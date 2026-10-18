import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import name_search_api
import clipboard_companion
import wcl_sync
import name_search


class MetadataClient:
    cache_scope='one'
    def __init__(self,fail=None):
        self.calls=[];self.fail=fail;self.cancel=threading.Event()

    def query_metadata(self,query):
        self.calls.append(query)
        if self.fail==len(self.calls): raise ValueError('API unavailable')
        chars={}
        for i,name,region,slug in re.findall(r'c(\d+):character\(name:("(?:[^"\\]|\\.)*"),serverRegion:("(?:[^"\\]|\\.)*"),serverSlug:("(?:[^"\\]|\\.)*")\)',query):
            name,region,slug=map(json.loads,(name,region,slug))
            number=int(slug[1:])
            chars['c'+i]=(dict(id=number+100,level=70 if number==0 else 90,name=name,classID=11,
                server=dict(id=number+1,name=slug,slug=slug,region=dict(slug=region.upper()))) if number in {0,80} else None)
        return {'data':{'gameData':{'classes':[{'id':11,'name':'Warrior'}]},'characterData':chars}}


class ApiSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='.test-api-',dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.cache=Path(self.temp.name)
        self.servers={'eu':[dict(id=i+1,slug='s'+str(i)) for i in range(81)]}
        self.member=dict(name='Zaratrass',region='eu',realm='',class_name='WARRIOR',min_level=90)

    def test_scans_all_realms_and_filters_historical_low_level_character(self):
        client=MetadataClient();search=name_search_api.ApiSearch(client,self.cache,self.servers)
        search.prepare([self.member])
        self.assertEqual(len(client.calls),2)
        self.assertEqual(search.for_member(self.member),[dict(realm_slug='s80',class_name='WARRIOR',level=90)])
        self.assertEqual(len(search.for_member(dict(self.member,min_level=None))),2)

    def test_restart_uses_complete_cached_search_without_any_api_call(self):
        first=name_search_api.ApiSearch(MetadataClient(),self.cache,self.servers)
        first.prepare([self.member])
        client=MetadataClient();second=name_search_api.ApiSearch(client,self.cache,self.servers)
        second.prepare([self.member])
        self.assertEqual(client.calls,[])
        self.assertEqual(second.for_member(self.member),first.for_member(self.member))

    def test_malformed_cached_matches_are_ignored_and_refetched(self):
        client=MetadataClient();search=name_search_api.ApiSearch(client,self.cache,self.servers)
        key=('eu','zaratrass')
        search._path(key).write_text(json.dumps(dict(fetched_at=time.time(),matches=[dict(realm_slug='s80',class_name='WARRIOR')])),'utf-8')
        search.prepare([self.member])
        self.assertEqual(search.for_member(self.member),[dict(realm_slug='s80',class_name='WARRIOR',level=90)])
        self.assertEqual(len(client.calls),2)

    def test_partial_scan_failure_is_not_unique_match_or_cached_absence(self):
        search=name_search_api.ApiSearch(MetadataClient(fail=2),self.cache,self.servers)
        with self.assertRaisesRegex(ValueError,'API unavailable'): search.prepare([self.member])
        self.assertEqual(search.results,{})
        self.assertEqual(list(self.cache.glob('*.json')),[])

    def test_unclassified_level_zero_record_does_not_abort_other_characters(self):
        class PlaceholderClient(MetadataClient):
            def query_metadata(self,query):
                raw=super().query_metadata(query)
                for char in raw['data']['characterData'].values():
                    if char and char['server']['slug']=='s0':
                        char['level']=0;char['classID']=0
                return raw
        client=PlaceholderClient()
        search=name_search_api.ApiSearch(client,self.cache,self.servers)
        members=[dict(self.member,name=name) for name in ('Démiurgê','Crazý','Spèctar')]
        search.prepare(members)
        for member in members:
            self.assertEqual(search.for_member(member),[dict(realm_slug='s80',class_name='WARRIOR',level=90)])

    def test_pre_squish_levels_above_current_cap_are_not_live_candidates(self):
        search=name_search_api.ApiSearch(MetadataClient(),self.cache,self.servers)
        search.results[('eu','zaratrass')]=[dict(realm_slug=str(level),class_name='WARRIOR',level=level) for level in (0,70,90,100,120)]
        self.assertEqual(search.for_member(self.member),[dict(realm_slug='90',class_name='WARRIOR',level=90)])

    def test_cancellation_is_not_cached(self):
        client=MetadataClient();client.cancel.set()
        search=name_search_api.ApiSearch(client,self.cache,self.servers)
        with self.assertRaisesRegex(ValueError,'cancelled'): search.prepare([self.member])
        self.assertEqual(client.calls,[])
        self.assertEqual(search.results,{})

    def test_bad_identity_blocks_only_its_name_without_caching_partial_matches(self):
        class BrokenIdentity(MetadataClient):
            def query_metadata(self,query):
                raw=super().query_metadata(query)
                for char in raw['data']['characterData'].values():
                    if char and char['name']=='Broken' and char['server']['slug']=='s0':
                        char['server']['id']=99999
                return raw
        search=name_search_api.ApiSearch(BrokenIdentity(),self.cache,self.servers)
        broken=dict(self.member,name='Broken')
        search.prepare([broken,self.member])
        self.assertEqual(search.for_member(self.member)[0]['realm_slug'],'s80')
        with self.assertRaisesRegex(ValueError,'server.id'):
            search.for_member(broken)
        self.assertNotIn(('eu','broken'),search.results)
        self.assertFalse(search._path(('eu','broken')).exists())

    def test_renamed_character_redirect_does_not_abort_regional_search(self):
        class Renamed(MetadataClient):
            def query_metadata(self,query):
                raw=super().query_metadata(query)
                for char in raw['data']['characterData'].values():
                    if char and char['server']['slug']=='s0':
                        char['name']='Tsupls'
                        char['server'].update(id=81,slug='s80')
                return raw
        search=name_search_api.ApiSearch(Renamed(),self.cache,self.servers)
        search.prepare([self.member])
        self.assertEqual(search.for_member(self.member),[dict(realm_slug='s80',class_name='WARRIOR',level=90)])

    def test_same_name_realm_redirect_is_validated_against_complete_catalogue(self):
        class Transferred(MetadataClient):
            def query_metadata(self,query):
                raw=super().query_metadata(query)
                for char in raw['data']['characterData'].values():
                    if char and char['server']['slug']=='s0':
                        char['server'].update(id=81,slug='s80');char['level']=90
                return raw
        search=name_search_api.ApiSearch(Transferred(),self.cache,self.servers)
        search.prepare([self.member])
        self.assertEqual(search.for_member(self.member),[dict(realm_slug='s80',class_name='WARRIOR',level=90)])

    def test_cache_scope_and_expiry_are_respected(self):
        first=name_search_api.ApiSearch(MetadataClient(),self.cache,self.servers)
        first.prepare([self.member])
        client=MetadataClient();client.cache_scope='another'
        second=name_search_api.ApiSearch(client,self.cache,self.servers);second.prepare([self.member])
        self.assertEqual(len(client.calls),2)
        with patch.object(name_search_api.time,'time',return_value=first.stamps[('eu','zaratrass')]+3601):
            first.prepare([self.member])
        self.assertEqual(len(first.client.calls),4)

    def test_metadata_uses_normal_client_quota_without_profile_refresh_cooldown(self):
        client=clipboard_companion.Client(token_provider=lambda:'fixture-token')
        self.addCleanup(client.budget.close)
        raw={'data':{'characterData':{},'rateLimitData':{'limitPerHour':3600,'pointsSpentThisHour':10,'pointsResetIn':3600}}}
        with patch.object(wcl_sync,'request_json',return_value=raw),patch.object(clipboard_companion.time,'sleep'):
            client.query_metadata('{characterData{}}');client.query_metadata('{characterData{}}')
        self.assertEqual(client.queries,2)
        self.assertEqual(client.budget.snapshot()['counters']['upstream_attempts'],2)

    def test_legacy_profile_cache_without_level_remains_usable_after_discovery(self):
        raw=MetadataClient().query_metadata('{characterData{c0:character(name:"Test",serverRegion:"eu",serverSlug:"s80"){id}}}')
        char=raw['data']['characterData']['c0']
        raw['data']['characterData']={'character':char}
        del char['level']
        member=dict(name='Test',region='eu',class_name='WARRIOR',min_level=90)
        self.assertIsNotNone(name_search.verified(raw,member,'s80'))
        char['level']=70
        self.assertIsNone(name_search.verified(raw,member,'s80'))


if __name__=='__main__': unittest.main()
