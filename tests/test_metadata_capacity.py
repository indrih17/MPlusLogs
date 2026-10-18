"""Metadata batches learn their own cost without spending live API quota."""
import copy
import sys
import unittest
from unittest.mock import patch

from test_addon import ROOT,api_fixture
sys.path.insert(0,str(ROOT/'tools'))
import clipboard_companion as bridge


class MetadataCapacityTests(unittest.TestCase):
    def setUp(self):
        self.client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(self.client.budget.close)

    def raw(self,cost=10,spent=100):
        return {'data':{'characterData':{'p0':None},'rateLimitData':{
            'limitPerHour':3600,'pointsSpentThisHour':spent,'pointsResetIn':500,
            'currentRequest':{'total':cost}}}}

    def metadata(self,raw,key='metadata:fixture'):
        return self.client._query(key,lambda _:raw,profile=False)

    def test_unknown_metadata_cost_probes_once_then_learns_full_batch(self):
        self.assertEqual(self.client.metadata_parallel_capacity(15),1)
        raw=self.raw()
        with patch.object(bridge.wcl,'request_json',return_value=raw), \
             patch.object(self.client.budget,'reserve',wraps=self.client.budget.reserve) as reserve:
            returned=self.client.query_metadata('query { lookup }')
        self.assertFalse(reserve.call_args.kwargs['pace'])
        self.assertFalse(reserve.call_args.kwargs['profile'])
        self.assertIs(returned,raw)
        self.assertEqual(returned['data']['rateLimitData']['currentRequest'],{'total':10})
        self.assertEqual(self.client.metadata_cost,10)
        self.assertIsNone(self.client.profile_cost)
        self.assertEqual(self.client.metadata_parallel_capacity(15),15)
        self.assertEqual(self.client.parallel_capacity(15),1)
        self.assertEqual(self.client.queries,1)
        self.assertEqual(self.client.budget.snapshot()['counters']['upstream_attempts'],1)

    def test_small_final_batch_cannot_reduce_full_metadata_batch_estimate(self):
        self.metadata(self.raw(20))
        self.metadata(self.raw(1,101),key='metadata:small')
        self.assertEqual(self.client.metadata_cost,20)

    def test_profile_and_metadata_prices_are_independent(self):
        raw=copy.deepcopy(api_fixture())
        raw['data']['rateLimitData']=self.raw(100)['data']['rateLimitData']
        self.client._query('profile',lambda _:raw)
        self.metadata(self.raw(2,102))
        self.assertEqual(self.client.profile_cost,100)
        self.assertEqual(self.client.metadata_cost,2)
        self.assertEqual(self.client.metadata_parallel_capacity(50),24)
        self.assertEqual(self.client.parallel_capacity(50),24)

    def test_metadata_wave_uses_the_same_price_as_point_admission(self):
        self.client.budget.observe(self.raw(100,3000)['data']['rateLimitData'])
        self.client.metadata_cost=2
        width=self.client.metadata_parallel_capacity(50)
        self.assertEqual(width,1)
        holds=[self.client.budget.reserve('metadata:wave-'+str(i),profile=False) for i in range(width)]
        self.assertEqual(len(holds),width)

    def test_metadata_capacity_counts_projected_reservations(self):
        self.metadata(self.raw(10,3200))
        self.assertEqual(self.client.metadata_parallel_capacity(50),2)
        self.client.budget.reserve('metadata:pending-one',profile=False)
        self.assertEqual(self.client.metadata_parallel_capacity(50),1)
        self.client.budget.reserve('metadata:pending-two',profile=False)
        self.assertEqual(self.client.metadata_parallel_capacity(50),0)
        self.assertEqual(self.client.budget.snapshot()['pointsSpentThisHour'],3200)

    def test_low_quota_or_local_exhaustion_prevents_parallel_metadata(self):
        self.metadata(self.raw(10,3250))
        self.assertEqual(self.client.metadata_parallel_capacity(50),0)
        self.client.queries=self.client.limit
        self.assertEqual(self.client.metadata_parallel_capacity(1),0)

    def test_metadata_wave_is_bounded_by_local_remaining_requests(self):
        self.metadata(self.raw())
        self.client.queries=self.client.limit-3
        self.assertEqual(self.client.metadata_parallel_capacity(50),3)

    def test_block_expiry_and_empty_input_are_respected(self):
        self.metadata(self.raw())
        snapshot=self.client.budget.snapshot()
        snapshot['blockedUntil']=bridge.time.time()+60
        with patch.object(self.client.budget,'snapshot',return_value=snapshot):
            self.assertEqual(self.client.metadata_parallel_capacity(50),0)
        snapshot['blockedUntil']=0
        snapshot['resetAt']=bridge.time.time()-1
        with patch.object(self.client.budget,'snapshot',return_value=snapshot):
            self.assertEqual(self.client.metadata_parallel_capacity(50),1)
        self.assertEqual(self.client.metadata_parallel_capacity(0),0)

    def test_invalid_metadata_cost_does_not_enable_a_large_wave(self):
        for cost in (None,True,0,-1,float('inf'),float('nan'),'10'):
            with self.subTest(cost=cost):
                self.metadata(self.raw(cost))
                self.assertIsNone(self.client.metadata_cost)
                self.assertEqual(self.client.metadata_parallel_capacity(10),1)


if __name__=='__main__':unittest.main()
