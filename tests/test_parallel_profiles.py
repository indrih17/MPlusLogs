"""Bounded profile requests preserve cache, budgets, order and failure isolation."""
import copy
from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import time
import unittest
import sys
import gc
import json
from pathlib import Path
from unittest.mock import patch

from test_addon import ROOT,api_fixture
sys.path.insert(0,str(ROOT/'tools'))
import build_database as builder
import clipboard_companion as bridge
import wcl_sync as wcl
from api_budget import Budget


class ParallelProfilesTests(unittest.TestCase):
    def setUp(self):
        # Prior GUI fixtures must be collected on the test main thread before
        # worker allocations can trigger Python's process-wide GC.
        gc.collect()
        folder=tempfile.TemporaryDirectory(prefix='.test-work-',dir=ROOT)
        self.addCleanup(folder.cleanup)
        self.cache=Path(folder.name)
        self.entries=[dict(name='Player'+chr(97+i),realm='Гордунни',server_slug='gordunni',region='eu') for i in range(12)]

    def raw(self,args):
        raw=copy.deepcopy(api_fixture())
        raw['data']['characterData']['character']['name']=args.name
        return raw

    def test_bounded_overlap_order_and_cache(self):
        lock=threading.Lock();active=peak=0;calls=[];events=[]
        def fetch(args):
            nonlocal active,peak
            with lock:
                active+=1;peak=max(peak,active);calls.append(args.name)
            time.sleep(.01)
            with lock:active-=1
            return self.raw(args)
        profiles,report=builder.build(self.entries,self.cache,max_fetch=12,fetcher=fetch,max_workers=3,
                                      progress=lambda done,total,entry:events.append(done))
        self.assertEqual(peak,3)
        self.assertEqual([p['name'] for p in profiles],[p['name'] for p in self.entries])
        self.assertEqual(report['fetched'],12)
        self.assertEqual(events,list(range(13)))
        _,cached=builder.build(self.entries,self.cache,fetcher=lambda _:self.fail('Cache must avoid API'),max_workers=3)
        self.assertEqual(cached['fetched'],0)
        self.assertEqual(cached['cacheHits'],12)

    def test_shared_per_run_limit_and_global_failure(self):
        calls=[]
        def fetch(args):calls.append(args.name);return self.raw(args)
        _,report=builder.build(self.entries,self.cache,max_fetch=2,fetcher=fetch,max_workers=3)
        self.assertEqual(len(calls),2)
        self.assertEqual(report['fetched'],2)
        other=self.cache/'failure';calls.clear()
        def fail(args):calls.append(args.name);raise wcl.APIError('WCL HTTP 429',429,60)
        _,report=builder.build(self.entries,other,max_fetch=12,fetcher=fail,max_workers=3)
        self.assertLessEqual(len(calls),3)
        self.assertEqual(report['fetched'],len(calls))
        self.assertEqual(len(report['errors']),12)

    def test_same_raw_cache_key_is_not_written_concurrently(self):
        calls=[]
        entries=[dict(self.entries[0],role=role) for role in ('DAMAGER','HEALER','TANK')]
        def fetch(args):calls.append(args.name);time.sleep(.01);return self.raw(args)
        _,report=builder.build(entries,self.cache,max_fetch=3,fetcher=fetch,max_workers=3)
        self.assertEqual(len(calls),1)
        self.assertEqual(report['fetched'],1)

    def test_quota_observations_do_not_go_backwards(self):
        budget=Budget(clock=lambda:1000)
        self.addCleanup(budget.close)
        for spent in (100,130,110):
            budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=spent,pointsResetIn=500))
        self.assertEqual(budget.snapshot()['pointsSpentThisHour'],130)

    def test_no_fixed_pause_in_either_api_mode(self):
        for personal in (True,False):
            with self.subTest(personal=personal):
                client=bridge.Client(token_provider=lambda:'fixture')
                self.addCleanup(client.budget.close)
                client.api_mode='personal' if personal else 'shared'
                with patch.object(client.budget,'reserve',return_value=0) as reserve:
                    client._query('one',lambda token:{})
                self.assertFalse(reserve.call_args.kwargs['pace'])

    def test_one_token_acquisition_across_concurrent_calls(self):
        client=bridge.Client()
        self.addCleanup(client.budget.close)
        def token(*args):time.sleep(.01);return 'fixture'
        with patch.object(client.budget,'reserve',return_value=0),patch.object(wcl,'access_token',side_effect=token) as auth:
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(lambda i:client._query(str(i),lambda token:{}),range(3)))
        self.assertEqual(auth.call_count,1)
        self.assertEqual(client.queries,3)

    def test_progressive_waves_wait_for_previous_responses_and_keep_order(self):
        for count,expected in ((15,[(14,1)]),(50,[(49,1)]),
                               (100,[(50,1),(49,51)])):
            with self.subTest(count=count):
                self.check_waves(count,expected)

    def check_waves(self,count,expected,memory=8*1024**3,max_fetch=None,cached=0):
        entries=[dict(self.entries[0],name='Player'+chr(97+i//26)+chr(97+i%26)) for i in range(100)]
        entries=entries[:count]
        cache=self.cache/str(count)/str(memory)/str(cached)
        if cached:
            builder.build(entries[:cached],cache,max_fetch=cached,fetcher=self.raw)
        outer=self
        class Fetcher:
            def __init__(self):self.done=0;self.waves=[];self.lock=threading.Lock()
            def __call__(self,args):
                time.sleep(.005)
                with self.lock:self.done+=1
                return outer.raw(args)
            def parallel_capacity(self,desired):
                self.waves.append((desired,self.done))
                return desired
        fetch=Fetcher()
        with patch.object(builder,'_profile_resources',return_value=(memory,None)),patch.object(builder.time,'process_time',return_value=0),patch.object(builder.statistics,'median',return_value=.005):
            profiles,report=builder.build(entries,cache,max_fetch=count if max_fetch is None else max_fetch,
                                          fetcher=fetch,max_workers=50)
        self.assertEqual(fetch.waves,expected)
        self.assertEqual(report['fetched'],count-cached if max_fetch is None else max_fetch)
        self.assertEqual([p['name'] for p in profiles],[p['name'] for p in entries[:len(profiles)]])
        self.assertEqual(report['cacheHits'],cached)
        return report

    def test_cached_entries_do_not_inflate_remaining_network_wave(self):
        self.check_waves(100,[(14,1)],cached=85)

    def test_wave_sizes_obey_remaining_request_limit(self):
        report=self.check_waves(100,[(14,1)],max_fetch=15)
        self.assertEqual(len(report['errors']),85)

    def test_weak_pc_and_unknown_resources_limit_actual_waves(self):
        self.check_waves(50,[(7,1),(7,8),(7,15),(7,22),(7,29),(7,36),(7,43)],memory=700*1024**2)
        self.check_waves(50,[(13,1),(12,14),(12,26),(12,38)],memory=None)

    def test_aliases_are_not_counted_as_network_work(self):
        entries=[dict(self.entries[0],name='Player'+chr(97+i),role=role)
                 for i in range(5) for role in ('DAMAGER','TANK')]
        calls=[];waves=[]
        def fetch(args):calls.append(args.name);return self.raw(args)
        fetch.parallel_capacity=lambda desired:waves.append(desired) or desired
        with patch.object(builder,'_profile_resources',return_value=(8*1024**3,None)):
            profiles,report=builder.build(entries,self.cache,max_fetch=10,fetcher=fetch,max_workers=50)
        self.assertEqual(waves,[4])
        self.assertEqual(report['fetched'],5)
        self.assertEqual(len(profiles),10)
        self.assertEqual([p['role'] for p in profiles],[e['role'] for e in entries])

    def test_adaptive_global_stop_preserves_retry_after_and_stale_cache(self):
        builder.build(self.entries,self.cache,max_fetch=12,fetcher=self.raw,now=1000)
        calls=[]
        def fail(args):calls.append(args.name);raise wcl.APIError('WCL HTTP 429',429,720)
        fail.parallel_capacity=lambda desired:desired
        _,report=builder.build(self.entries,self.cache,ttl_hours=1,max_fetch=12,fetcher=fail,max_workers=50,now=10000)
        self.assertEqual(len(calls),1)
        self.assertEqual(report['fetched'],1)
        self.assertEqual(report['profiles'],12)
        self.assertEqual(len(report['errors']),12)
        self.assertTrue(all(e['retry_at']==10720 for e in report['errors']))

    def test_offline_cache_and_retry_cooldown_never_need_capacity(self):
        builder.build(self.entries,self.cache,max_fetch=12,fetcher=self.raw,now=1000)
        def fetch(args):self.fail('No network during cooldown/offline')
        fetch.parallel_capacity=lambda desired:self.fail('Cache needs no capacity')
        _,report=builder.build(self.entries,self.cache,fetcher=fetch,max_workers=50,offline=True,now=100000)
        self.assertEqual(report['profiles'],12)
        self.assertEqual(report['fetched'],0)
        for entry in self.entries:
            path=builder.cache_path(self.cache,entry)
            record=builder.read_cache(path);record['retry_until']=200000
            builder.atomic_write(path,json.dumps(record))
        _,report=builder.build(self.entries,self.cache,fetcher=fetch,max_workers=50,now=100000)
        self.assertEqual(report['profiles'],12)
        self.assertEqual(report['fetched'],0)

    def test_policy_reduces_cpu_pressure_and_network_congestion_without_sleep(self):
        with patch.object(builder,'_profile_resources',return_value=(8*1024**3,None)),patch.object(builder.time,'sleep',side_effect=AssertionError('No fixed pauses')):
            policy=builder._ProfileWaves(50)
            self.assertEqual(policy.desired(99),50)
            policy.observe(40,1,.8,[.9]*40)
            self.assertEqual(policy.desired(59),20)
            policy.observe(20,1,.1,[.9]*20)
            self.assertEqual(policy.desired(59),20)
            policy.observe(20,1,.1,[.9]*20)
            self.assertEqual(policy.desired(50),25)
            policy.observe(25,3,.1,[2.8]*25)
            self.assertEqual(policy.desired(59),12)

    def test_policy_can_recover_from_a_single_worker_after_pressure_clears(self):
        with patch.object(builder,'_profile_resources',return_value=(8*1024**3,None)):
            policy=builder._ProfileWaves(50)
            policy.observe(1,1,.9,[.9])
            self.assertEqual(policy.desired(50),1)
            for _ in range(2):policy.observe(1,1,.1,[.9])
            self.assertEqual(policy.desired(50),2)

    def test_cpu_feedback_reduces_the_next_actual_wave(self):
        outer=self
        class Fetcher:
            def __init__(self):self.done=0;self.waves=[];self.lock=threading.Lock()
            def __call__(self,args):
                time.sleep(.06)
                with self.lock:self.done+=1
                return outer.raw(args)
            def parallel_capacity(self,desired):
                self.waves.append((desired,self.done));return desired
        entries=[dict(self.entries[0],name='Player'+chr(97+i//26)+chr(97+i%26)) for i in range(100)]
        fetch=Fetcher()
        # Probe is I/O-bound; first parallel wave simulates expensive local
        # parsing/cache work. Later waves have no extra CPU pressure.
        with patch.object(builder,'_profile_resources',return_value=(8*1024**3,None)),patch.object(builder.time,'process_time',side_effect=[0,0,0,10,10,10,10,10]):
            profiles,report=builder.build(entries,self.cache,max_fetch=100,fetcher=fetch,max_workers=50)
        self.assertEqual(fetch.waves,[(50,1),(25,51),(24,76)])
        self.assertEqual(report['fetched'],100)
        self.assertEqual([p['name'] for p in profiles],[e['name'] for e in entries])

    def test_quota_rejection_after_probe_stops_all_later_network_calls(self):
        calls=[]
        def fetch(args):calls.append(args.name);return self.raw(args)
        fetch.parallel_capacity=lambda desired:0
        _,report=builder.build(self.entries,self.cache,max_fetch=12,fetcher=fetch,max_workers=50)
        self.assertEqual(calls,[self.entries[0]['name']])
        self.assertEqual(report['fetched'],1)
        self.assertEqual(len(report['errors']),11)
        self.assertTrue(all(e['error_code']=='budget' for e in report['errors']))

    def test_cancellation_before_probe_does_not_call_fetcher(self):
        def fetch(args):self.fail('Cancelled batch must not call upstream')
        fetch.cancel=threading.Event();fetch.cancel.set()
        _,report=builder.build(self.entries,self.cache,max_fetch=12,fetcher=fetch,max_workers=50)
        self.assertEqual(report['fetched'],0)
        self.assertEqual(len(report['errors']),12)

    def test_zero_request_limit_and_negative_cache_need_no_upstream(self):
        def fetch(args):self.fail('No network budget')
        fetch.parallel_capacity=lambda desired:self.fail('No budget needs no capacity')
        _,report=builder.build(self.entries,self.cache,max_fetch=0,fetcher=fetch,max_workers=50)
        self.assertEqual(report['fetched'],0)
        self.assertEqual(len(report['errors']),12)
        for entry in self.entries:
            builder.atomic_write(builder.cache_path(self.cache,entry),json.dumps(
                dict(fetched_at=1000,negative=True,error='No profile',error_code='no_profile')))
        _,report=builder.build(self.entries,self.cache,fetcher=fetch,max_workers=50,now=1001)
        self.assertEqual(report['negativeCacheHits'],12)
        self.assertEqual(report['fetched'],0)

    def test_system_cpu_pressure_and_memory_are_resampled(self):
        samples=[(8*1024**3,(0,100)),(8*1024**3,(5,200)),(300*1024**2,(80,300))]
        with patch.object(builder,'_profile_resources',side_effect=samples):
            policy=builder._ProfileWaves(50)
            self.assertEqual(policy.desired(100),50)
            self.assertEqual(policy.desired(100),8)
            self.assertEqual(policy.desired(100),4)

    def test_explicit_worker_bound_and_memory_fallback(self):
        with patch.object(builder,'_profile_resources',return_value=(None,None)):
            self.assertEqual(builder._ProfileWaves(50).desired(100),15)
            self.assertEqual(builder._ProfileWaves(5).desired(100),5)

    def test_quota_capacity_shrinks_the_wave_and_stops_when_reserve_is_reached(self):
        for spent,expected in ((100,50),(3200,2),(3250,0)):
            client=bridge.Client(token_provider=lambda:'fixture')
            self.addCleanup(client.budget.close)
            client.profile_cost=10
            client.budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=spent,pointsResetIn=500,currentRequest={'total':10}))
            self.assertEqual(client.parallel_capacity(50),expected)

    def test_wave_capacity_accounts_for_reserved_points_before_replies_arrive(self):
        client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(client.budget.close)
        client.profile_cost=10
        client.budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=3200,pointsResetIn=500,currentRequest={'total':10}))
        self.assertEqual(client.parallel_capacity(50),2)
        client.budget.reserve('pending-one')
        self.assertEqual(client.parallel_capacity(50),1)
        client.budget.reserve('pending-two')
        self.assertEqual(client.parallel_capacity(50),0)
        self.assertEqual(client.budget.snapshot()['pointsSpentThisHour'],3200)

    def test_parallel_quota_delta_is_not_mistaken_for_one_request_cost(self):
        budget=Budget(clock=lambda:1000)
        self.addCleanup(budget.close)
        for spent in (100,600,110):
            budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=spent,pointsResetIn=500,currentRequest={'total':10}))
        self.assertEqual(budget.snapshot()['pointsSpentThisHour'],600)
        self.assertEqual(budget.snapshot()['largestObservedCost'],10)

    def test_unknown_cost_stays_at_one_and_readable_probe_supplies_cost(self):
        client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(client.budget.close)
        self.assertEqual(client.parallel_capacity(10),1)
        raw=self.raw(builder.arguments(self.entries[0]))
        raw['data']['rateLimitData']=dict(limitPerHour=3600,pointsSpentThisHour=10,pointsResetIn=500,currentRequest={'total':10})
        client._query('probe',lambda _:raw)
        self.assertEqual(client.profile_cost,10)
        self.assertEqual(client.parallel_capacity(10),10)


if __name__=='__main__':unittest.main()
