import gc
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from name_search_api import ApiSearch


class EmptyClient:
    profile_workers=50

    def __init__(self):self.calls=[]

    def metadata_parallel_capacity(self,count):return count

    def query_metadata(self,query):
        self.calls.append(query)
        aliases=re.findall(r'(c\d+):character\(',query)
        return {'data':{'gameData':{'classes':[{'id':1,'name':'Warrior'}]},
                        'characterData':dict.fromkeys(aliases)}}


class LookupReadyTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.folder=tempfile.TemporaryDirectory(prefix='.test-ready-',dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.folder.cleanup)
        self.cache=Path(self.folder.name)
        self.servers={'eu':[dict(id=i+1,slug='s'+str(i)) for i in range(161)]}

    def member(self,index,name='Player',realm=''):
        return dict(index=index,name=name,region='eu',realm=realm,class_name='WARRIOR',min_level=90)

    def test_known_and_full_cached_members_ready_before_http(self):
        ready=[]
        outer=self
        class Client(EmptyClient):
            def query_metadata(self,query):
                outer.assertEqual(ready,[1,2,3])
                return super().query_metadata(query)
        search=ApiSearch(Client(),self.cache,self.servers)
        key=('eu','cached')
        # Deliberately unsorted old disk entries must be canonical on reuse.
        matches=[dict(realm_slug='s9',class_name='WARRIOR',level=90),
                 dict(realm_slug='s1',class_name='WARRIOR',level=90)]
        search._path(key).write_text(json.dumps(dict(fetched_at=time.time(),matches=matches)))
        members=[self.member(1,realm='s1'),self.member(2,'Cached'),
                 self.member(3,'Cached'),self.member(4,'Fresh')]
        search.prepare(members,on_ready=lambda member:ready.append(member['index']))
        self.assertEqual(ready,[1,2,3,4])
        self.assertEqual([c['realm_slug'] for c in search.results[key]],['s1','s9'])

    def test_incomplete_scan_never_notifies_unknown_member(self):
        ready=[]
        class Client(EmptyClient):
            def query_metadata(self,query):
                if self.calls:raise ValueError('Stopped')
                return super().query_metadata(query)
        search=ApiSearch(Client(),self.cache,self.servers)
        with self.assertRaisesRegex(ValueError,'Stopped'):
            search.prepare([self.member(1)],on_ready=ready.append)
        self.assertEqual(ready,[])
        self.assertEqual(search.results,{})

    def test_duplicate_members_ready_once_after_complete_checkpoint(self):
        client=EmptyClient();search=ApiSearch(client,self.cache,self.servers)
        key=('eu','player')
        search._save_checkpoint(key,{s['slug']:dict(fetched_at=time.time(),matches=[])
                                     for s in self.servers['eu']})
        first=self.member(1);second=self.member(2)
        ready=[]
        search.prepare([first,second,first],on_ready=ready.append)
        self.assertEqual(ready,[first,second])
        self.assertEqual(client.calls,[])
        self.assertEqual(search.for_member(first),[])

    def test_completed_member_survives_later_lookup_error(self):
        client=EmptyClient()
        class Search(ApiSearch):
            def _request_batches(self,tasks,progress):
                yield tasks[:1],{'data':{'gameData':{'classes':[{'id':1,'name':'Warrior'}]},
                                         'characterData':{'c0':None}}}
                raise ValueError('Later network failure')
        search=Search(client,self.cache,{'eu':[dict(id=1,slug='s0')]})
        first=self.member(1,'First');second=self.member(2,'Second');ready=[]
        with self.assertRaisesRegex(ValueError,'Later network failure'):
            search.prepare([first,second],on_ready=ready.append)
        self.assertEqual(ready,[first])
        self.assertEqual(search.for_member(first),[])
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            search.for_member(second)

    def test_members_without_index_use_object_identity(self):
        client=EmptyClient();search=ApiSearch(client,self.cache,self.servers)
        first=self.member(1,realm='s0');del first['index']
        second=dict(first);ready=[]
        search.prepare([first,second,first],on_ready=ready.append)
        self.assertEqual(len(ready),2)
        self.assertIs(ready[0],first)
        self.assertIs(ready[1],second)

    def test_successful_batch_streams_before_slow_wave_neighbor(self):
        release=threading.Event();slow_started=threading.Event();returned=threading.Event()
        class Client(EmptyClient):
            def query_metadata(self,query):
                if 'serverSlug:"s160"' in query:
                    slow_started.set()
                    if not release.wait(3):raise ValueError('Test release timed out')
                return super().query_metadata(query)
        search=ApiSearch(Client(),self.cache,self.servers)
        key=('eu','player')
        tasks=[(key,'Player',s) for s in self.servers['eu']]
        batches=search._request_batches(tasks,None)
        self.assertEqual(next(batches)[0][0][2]['slug'],'s0')
        results=[];failures=[]
        def consume_one():
            try:results.append(next(batches))
            except Exception as exc:failures.append(exc)
            finally:returned.set()
        worker=threading.Thread(target=consume_one)
        worker.start()
        try:
            self.assertTrue(slow_started.wait(1))
            self.assertTrue(returned.wait(1),'Fast completed batch waited for its slow neighbor')
        finally:
            release.set();worker.join(3)
            list(batches)
        self.assertEqual(failures,[])
        self.assertEqual(results[0][0][0][2]['slug'],'s80')


if __name__=='__main__':unittest.main()
