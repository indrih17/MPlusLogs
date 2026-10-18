"""Offline regression coverage for complete identity scans and resumable work."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_name_search_api import MetadataClient
from name_search_api import ApiSearch


class RealmResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='.test-resume-',dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.cache=Path(self.temp.name)
        self.servers={'eu':[dict(id=i+1,slug='s'+str(i)) for i in range(81)]}
        self.member=dict(name='Test',region='eu',realm='',class_name='WARRIOR',min_level=90)

    def interrupted(self):
        search=ApiSearch(MetadataClient(fail=2),self.cache,self.servers)
        with self.assertRaisesRegex(ValueError,'API unavailable'):search.prepare([self.member])
        with self.assertRaisesRegex(ValueError,'Incomplete'):search.for_member(self.member)
        self.assertFalse(search._path(('eu','test')).exists())
        return search

    def test_restart_only_fetches_missing_alias_and_cannot_expose_partial_identity(self):
        self.interrupted()
        client=MetadataClient();search=ApiSearch(client,self.cache,self.servers)
        search.prepare([self.member])
        self.assertEqual(len(client.calls),1)
        self.assertEqual(client.calls[0].count(':character('),1)
        self.assertIn('serverSlug:"s80"',client.calls[0])
        self.assertEqual(search.for_member(self.member),[dict(realm_slug='s80',class_name='WARRIOR',level=90)])
        self.assertFalse(search._checkpoint_path(('eu','test')).exists())

    def test_expired_checkpoint_rechecks_all_realms(self):
        self.interrupted()
        client=MetadataClient();search=ApiSearch(client,self.cache,self.servers)
        with patch('name_search_api.time.time',return_value=time.time()+301):search.prepare([self.member])
        self.assertEqual(len(client.calls),2)
        self.assertEqual(sum(q.count(':character(') for q in client.calls),81)

    def test_scope_and_catalogue_changes_never_reuse_old_partial_scans(self):
        self.interrupted()
        variants=[('other',self.servers),('one',{'eu':self.servers['eu']+[dict(id=82,slug='s81')]})]
        for scope,servers in variants:
            with self.subTest(scope=scope):
                client=MetadataClient();client.cache_scope=scope
                search=ApiSearch(client,self.cache,servers);search.prepare([self.member])
                self.assertEqual(sum(q.count(':character(') for q in client.calls),len(servers['eu']))

    def test_cancel_keeps_validated_probe_for_retry(self):
        class CancelAfterProbe(MetadataClient):
            def query_metadata(self,query):
                result=super().query_metadata(query);self.cancel.set();return result
        client=CancelAfterProbe();search=ApiSearch(client,self.cache,self.servers)
        with self.assertRaisesRegex(ValueError,'cancelled'):search.prepare([self.member])
        retry=MetadataClient();ApiSearch(retry,self.cache,self.servers).prepare([self.member])
        self.assertEqual(sum(q.count(':character(') for q in retry.calls),1)

    def test_invalid_and_missing_aliases_are_retried_but_valid_aliases_survive(self):
        class InvalidAliases(MetadataClient):
            def query_metadata(self,query):
                result=super().query_metadata(query)
                if len(self.calls)==1:
                    result['data']['characterData']['c0']['server']['id']=99999
                    del result['data']['characterData']['c1']
                return result
        search=ApiSearch(InvalidAliases(),self.cache,self.servers);search.prepare([self.member])
        with self.assertRaisesRegex(ValueError,'Incomplete|Invalid'):search.for_member(self.member)
        retry=MetadataClient();search=ApiSearch(retry,self.cache,self.servers);search.prepare([self.member])
        self.assertEqual(sum(q.count(':character(') for q in retry.calls),2)
        self.assertIn('serverSlug:"s0"',retry.calls[0]);self.assertIn('serverSlug:"s1"',retry.calls[0])
        self.assertEqual(len(search.for_member(self.member)),1)

    def test_graphql_alias_error_is_never_negative_cached(self):
        class GraphQLError(MetadataClient):
            def query_metadata(self,query):
                result=super().query_metadata(query)
                if len(self.calls)==1:
                    result['data']['characterData']['c0']=None
                    result['errors']=[dict(message='unavailable',path=['characterData','c0'])]
                return result
        search=ApiSearch(GraphQLError(),self.cache,self.servers);search.prepare([self.member])
        with self.assertRaisesRegex(ValueError,'Incomplete'):search.for_member(self.member)
        retry=MetadataClient();ApiSearch(retry,self.cache,self.servers).prepare([self.member])
        self.assertEqual(sum(q.count(':character(') for q in retry.calls),1)
        self.assertIn('serverSlug:"s0"',retry.calls[0])

    def test_parallel_sibling_success_survives_failed_wave(self):
        class ParallelFailure(MetadataClient):
            profile_workers=50
            def __init__(self):
                super().__init__();self.success=threading.Event()
            def metadata_parallel_capacity(self,desired):return desired
            def query_metadata(self,query):
                # First probe covers s0..s79; the second and third batches overlap.
                if 'serverSlug:"s80"' in query:
                    if not self.success.wait(2):raise AssertionError('Sibling did not run')
                    raise ValueError('failed sibling')
                raw=super().query_metadata(query)
                if 'serverSlug:"s160"' in query:self.success.set()
                return raw
        servers={'eu':[dict(id=i+1,slug='s'+str(i)) for i in range(240)]}
        client=ParallelFailure();search=ApiSearch(client,self.cache,servers)
        with patch('name_search_api.builder._profile_resources',return_value=(8*1024**3,None)):
            with self.assertRaisesRegex(ValueError,'failed sibling'):search.prepare([self.member])
        self.assertEqual(search.results,{})
        retry=MetadataClient();search=ApiSearch(retry,self.cache,servers);search.prepare([self.member])
        self.assertEqual(sum(q.count(':character(') for q in retry.calls),80)
        self.assertIn('serverSlug:"s80"',retry.calls[0])
        self.assertNotIn('serverSlug:"s160"',retry.calls[0])

    def test_complete_name_is_saved_even_when_later_name_fails(self):
        servers={'eu':self.servers['eu'][:80]}
        client=MetadataClient(fail=2);search=ApiSearch(client,self.cache,servers)
        with self.assertRaisesRegex(ValueError,'API unavailable'):
            search.prepare([self.member,dict(self.member,name='Other')])
        self.assertTrue(search._path(('eu','test')).exists())
        self.assertFalse(search._path(('eu','other')).exists())
        retry=MetadataClient();search=ApiSearch(retry,self.cache,servers)
        search.prepare([self.member,dict(self.member,name='Other')])
        self.assertEqual(sum(q.count(':character(') for q in retry.calls),80)
        self.assertNotIn('name:"Test"',retry.calls[0])

    def test_positive_ttl_six_hours_negative_ttl_five_minutes_and_refresh(self):
        search=ApiSearch(MetadataClient(),self.cache,self.servers);search.prepare([self.member])
        stamp=search.stamps[('eu','test')]
        with patch('name_search_api.time.time',return_value=stamp+3601):search.prepare([self.member])
        self.assertEqual(len(search.client.calls),2)
        with patch('name_search_api.time.time',return_value=stamp+21600):search.prepare([self.member])
        self.assertEqual(len(search.client.calls),4)
        search.prepare([self.member],refresh=True)
        self.assertEqual(len(search.client.calls),6)
        class Absent(MetadataClient):
            def query_metadata(self,query):
                raw=super().query_metadata(query)
                raw['data']['characterData']={key:None for key in raw['data']['characterData']}
                return raw
        client=Absent();search=ApiSearch(client,self.cache,self.servers)
        member=dict(self.member,name='Absent');search.prepare([member]);stamp=search.stamps[('eu','absent')]
        with patch('name_search_api.time.time',return_value=stamp+299):search.prepare([member])
        self.assertEqual(len(client.calls),2)
        with patch('name_search_api.time.time',return_value=stamp+300):search.prepare([member])
        self.assertEqual(len(client.calls),4)

    def test_refresh_discards_checkpoint_and_old_schema_is_ignored(self):
        search=self.interrupted();client=MetadataClient();search=ApiSearch(client,self.cache,self.servers)
        search.prepare([self.member],refresh=True)
        self.assertEqual(sum(q.count(':character(') for q in client.calls),81)
        other=dict(self.member,name='Old')
        path=search._checkpoint_path(('eu','old'))
        path.write_text(json.dumps(dict(version=0,fetched_at=time.time(),entries={
            s['slug']:dict(fetched_at=time.time(),matches=[]) for s in self.servers['eu']})),encoding='utf-8')
        client.calls.clear();search.prepare([other])
        self.assertEqual(sum(q.count(':character(') for q in client.calls),81)


if __name__=='__main__':unittest.main()
