"""Group profiles start as soon as their own realm identity is ready."""
import copy
import gc
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
from test_addon import api_fixture
import name_search
import name_search_api
import realm_resolver


class PipelineClient:
    profile_workers=3
    cache_scope='pipeline-fixture'
    def __init__(self,cache):
        self.cancel=threading.Event()
        self.known_started=threading.Event()
        self.fast_loaded=threading.Event()
        self.events=[]
        servers=[dict(id=i+1,slug='gordunni' if i==0 else 's'+str(i)) for i in range(80)]
        self.name_search=name_search_api.ApiSearch(self,cache,{'eu':servers})

    def metadata_parallel_capacity(self,remaining):return min(3,remaining)

    def query_metadata(self,query):
        self.events.append('lookup')
        if not self.known_started.wait(1):raise AssertionError('Known-realm profile was blocked by global preparation')
        if 'Slow' in query and not self.fast_loaded.wait(1):
            raise AssertionError('Ready character was blocked until another realm scan finished')
        chars={}
        pattern=r'c(\d+):character\(name:("(?:[^"\\]|\\.)*"),serverRegion:("(?:[^"\\]|\\.)*"),serverSlug:("(?:[^"\\]|\\.)*")\)'
        for index,name,region,slug in re.findall(pattern,query):
            name,region,slug=map(json.loads,(name,region,slug))
            chars['c'+index]=(dict(id=123,name=name,classID=51,level=90,
                server=dict(id=1,name='Гордунни',slug=slug,region=dict(slug=region))) if slug=='gordunni' else None)
        return {'data':{'characterData':chars,'gameData':{'classes':[{'id':51,'name':'Warrior'}]}}}

    def __call__(self,args):
        self.events.append('profile:'+args.name)
        if args.name=='Known':self.known_started.set()
        raw=copy.deepcopy(api_fixture())
        char=raw['data']['characterData']['character']
        char.update(name=args.name,classID=51,level=90)
        char['server'].update(id=1,name='Гордунни',slug='gordunni')
        char['damage']=char.pop('performance');char['healing']=copy.deepcopy(char['damage'])
        raw['data']['worldData']={'server':{'id':1}}
        raw['data']['gameData']={'classes':[{'id':51,'name':'Warrior'}]}
        if args.name=='Fast':self.fast_loaded.set()
        return raw


class GroupPipelineTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.temp=tempfile.TemporaryDirectory(prefix='.test-pipeline-',dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.cache=Path(self.temp.name)

    def test_known_and_individually_ready_profiles_overlap_other_realm_search(self):
        client=PipelineClient(self.cache)
        body=('MPLN1\nN\t1\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\t\tFast\tWARRIOR\tDAMAGER\tsearch\t90\n'
              'N\t3\teu\t\tSlow\tWARRIOR\tDAMAGER\tsearch\t90\n')
        reply=name_search.reply(body,realm_resolver.load_mappings(),self.cache,client)
        rows=[line.split('\t') for line in reply.splitlines() if line.startswith('P\t')]
        self.assertEqual([row[1] for row in rows],['1','2','3'],reply)
        self.assertEqual([row[4] for row in rows],['Known','Fast','Slow'])
        self.assertLess(client.events.index('profile:Known'),client.events.index('lookup'))
        self.assertTrue(client.fast_loaded.is_set())

    def test_explicit_leader_is_the_first_useful_probe_without_reordering_rows(self):
        client=PipelineClient(self.cache)
        body=('MPLN1\nN\t1\teu\tГордунни\tOther\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tleader\t90\n')
        reply=name_search.reply(body,realm_resolver.load_mappings(),self.cache,client)
        self.assertEqual(client.events[0],'profile:Known')
        self.assertNotIn('lookup',client.events)
        self.assertEqual([r.split('\t')[4] for r in reply.splitlines() if r.startswith('P\t')],['Other','Known'])

    def test_full_identity_cache_starts_profiles_without_lookup_requests(self):
        client=PipelineClient(self.cache)
        key=('eu','fast')
        client.name_search.results[key]=[dict(realm_slug='gordunni',class_name='WARRIOR',level=90)]
        client.name_search.stamps[key]=time.time()
        body=('MPLN1\nN\t1\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\t\tFast\tWARRIOR\tDAMAGER\tsearch\t90\n')
        reply=name_search.reply(body,realm_resolver.load_mappings(),self.cache,client)
        self.assertNotIn('lookup',client.events)
        self.assertEqual(sum(r.startswith('P\t') for r in reply.splitlines()),2)

    def test_late_lookup_error_preserves_already_ready_profiles(self):
        class LateError(PipelineClient):
            def query_metadata(self,query):
                if 'Slow' in query:
                    if not self.fast_loaded.wait(1):raise AssertionError('Fast profile must run before slow lookup fails')
                    raise ValueError('Late lookup failed')
                return super().query_metadata(query)
        client=LateError(self.cache)
        body=('MPLN1\nN\t1\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\t\tFast\tWARRIOR\tDAMAGER\tsearch\t90\n'
              'N\t3\teu\t\tSlow\tWARRIOR\tDAMAGER\tsearch\t90\n')
        reply=name_search.reply(body,realm_resolver.load_mappings(),self.cache,client)
        self.assertEqual([r.split('\t')[:2] for r in reply.splitlines()[1:]],[['P','1'],['P','2'],['F','3']])

    def test_duplicate_profile_keys_share_one_fetch_and_atomic_cache_write(self):
        class DuplicateClient(PipelineClient):
            def __call__(self,args):
                if args.name=='Duplicate':time.sleep(.015)
                return super().__call__(args)
        client=DuplicateClient(self.cache)
        body=('MPLN1\nN\t1\teu\tГордунни\tDuplicate\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\tГордунни\tDuplicate\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t3\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tleader\t90\n')
        reply=name_search.reply(body,realm_resolver.load_mappings(),self.cache,client)
        self.assertEqual(client.events.count('profile:Duplicate'),1)
        self.assertEqual(sum(r.startswith('P\t') for r in reply.splitlines()),3)
        self.assertEqual(list(self.cache.glob('*.tmp')),[])

    def test_pipeline_progress_counts_people_and_stays_monotonic(self):
        client=PipelineClient(self.cache)
        body=('MPLN1\nN\t1\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\t\tFast\tWARRIOR\tDAMAGER\tsearch\t90\n'
              'N\t3\teu\t\tSlow\tWARRIOR\tDAMAGER\tsearch\t90\n')
        events=[]
        name_search.reply(body,realm_resolver.load_mappings(),self.cache,client,progress=events.append)
        self.assertTrue(all(e['stage']=='search' and e['total']==3 for e in events))
        completed=[e['completed'] for e in events]
        self.assertEqual(completed,sorted(completed))
        self.assertEqual((completed[0],completed[-1]),(0,3))

    def test_cancelled_group_does_not_start_any_new_http(self):
        client=PipelineClient(self.cache);client.cancel.set()
        body=('MPLN1\nN\t1\teu\tГордунни\tKnown\tWARRIOR\tDAMAGER\tknown\t90\n'
              'N\t2\teu\t\tFast\tWARRIOR\tDAMAGER\tsearch\t90\n')
        reply=name_search.reply(body,realm_resolver.load_mappings(),self.cache,client)
        self.assertEqual(client.events,[])
        self.assertEqual(sum(r.startswith('F\t') for r in reply.splitlines()),2)


if __name__=='__main__':unittest.main()
