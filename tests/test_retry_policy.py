"""Failure-specific retry gates cross actual Client admissions and cache reads."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_addon import ROOT, api_fixture
sys.path.insert(0,str(ROOT/'tools'))
import build_database as builder
import clipboard_companion as bridge
import wcl_sync as wcl
from api_budget import Budget, BudgetError


class RetryPolicyTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix='.test-retry-policy-',dir=ROOT)
        self.addCleanup(folder.cleanup)
        self.cache=Path(folder.name)
        self.now=1000
        self.entry=dict(name='Alice',realm='Гордунни',server_slug='gordunni',region='eu')
        self.client=self.make_client()
        self.calls=[]
        self.should_fail=True
        self.error=lambda:OSError('Safe network failure')
        self.fetch=self.enterContext(patch.object(wcl,'fetch',side_effect=self.response))

    def make_client(self, generation='', persistent=False):
        client=bridge.Client(token_provider=lambda:'test-token',auth_generation=generation,
                             state_path=self.cache/'budget.sqlite3' if persistent else None)
        client.budget.clock=lambda:self.now
        self.addCleanup(client.budget.close)
        return client

    def response(self,args,*a,**kw):
        self.calls.append(args.name)
        if self.should_fail:raise self.error()
        raw=copy.deepcopy(api_fixture())
        raw['data']['characterData']['character']['name']=args.name
        return raw

    def build(self, client=None, **kwargs):
        return builder.build([self.entry],self.cache,fetcher=client or self.client,now=self.now,**kwargs)

    def cached(self):return builder.read_cache(builder.cache_path(self.cache,self.entry))

    def test_network_recovers_after_fifteen_seconds_through_actual_client(self):
        _,report=self.build()
        self.assertEqual(report['errors'][0]['retry_at'],1015)
        self.now=1014;self.build()
        self.assertEqual(len(self.calls),1)
        self.now=1015;self.should_fail=False
        profiles,report=self.build()
        self.assertEqual(len(profiles),1,report['errors'])
        self.assertEqual(len(self.calls),2)
        self.assertNotIn('failure_count',self.cached())
        with self.assertRaises(BudgetError):self.client(builder.arguments(self.entry))

    def test_cached_clicks_do_not_slide_or_deepen_the_backoff(self):
        for expected_count,delay in enumerate((15,30,60,120,120),1):
            start=self.now
            _,report=self.build()
            self.assertEqual(report['errors'][0]['retry_at'],start+delay)
            self.assertEqual(self.cached()['failure_count'],expected_count)
            self.now=start+delay-1;self.build();self.build()
            self.assertEqual(len(self.calls),expected_count)
            self.assertEqual(self.cached()['failure_count'],expected_count)
            self.assertEqual(self.cached()['retry_until'],start+delay)
            self.now=start+delay

    def test_success_resets_streak_after_success_cooldown(self):
        self.build();self.now=1015;self.should_fail=False;self.build()
        self.now=1315;self.should_fail=True
        _,report=self.build(refresh=True)
        self.assertEqual(report['errors'][0]['retry_at'],1330)
        self.assertEqual(self.cached()['failure_count'],1)

    def test_schema_uses_fixed_sixty_second_gate(self):
        self.error=lambda:wcl.APIError('Safe schema failure',code='schema')
        self.build();self.assertEqual(self.cached()['retry_until'],1060)
        self.now=1060;self.build();self.assertEqual(self.cached()['retry_until'],1120)
        self.assertEqual(len(self.calls),2)

    def test_explicit_short_quota_hint_has_no_five_minute_floor(self):
        self.error=lambda:wcl.APIError('WCL HTTP 429',429,7)
        self.build();self.assertEqual(self.cached()['retry_until'],1007)
        self.now=1007;self.should_fail=False
        profiles,report=self.build()
        self.assertEqual(len(profiles),1,report['errors'])
        self.assertEqual(len(self.calls),2)

    def test_quota_reset_and_server_hint_are_both_preserved(self):
        self.client.budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=0,pointsResetIn=900))
        self.error=lambda:wcl.APIError('WCL HTTP 429',429,1200)
        self.build();self.assertEqual(self.cached()['retry_until'],2200)
        self.now=2199;self.should_fail=False;self.build()
        self.assertEqual(len(self.calls),1)

    def test_reset_only_quota_error_uses_seven_second_hint(self):
        self.error=lambda:wcl.APIError('WCL HTTP 429',429,rate_limit=dict(
            limitPerHour=3600,pointsSpentThisHour=3599,pointsResetIn=7))
        self.build()
        self.assertEqual(self.cached()['retry_until'],1007)
        self.assertEqual(self.client.budget.snapshot()['blockedUntil'],1007)

    def test_auth_new_generation_bypasses_failed_cache_and_profile_gate(self):
        first=self.make_client('a'*32,persistent=True)
        self.error=lambda:wcl.APIError('Safe authentication failure',401,code='auth')
        self.build(first)
        self.assertEqual(self.cached()['retry_until'],1060)
        self.assertEqual(first.budget.snapshot()['blockedUntil'],0)
        same=self.make_client('a'*32,persistent=True)
        self.now=1001;self.build(same)
        self.assertEqual(len(self.calls),1)
        changed=self.make_client('b'*32,persistent=True)
        self.should_fail=False
        profiles,report=self.build(changed)
        self.assertEqual(len(profiles),1,report['errors'])
        self.assertEqual(len(self.calls),2)

    def test_relogin_preserves_success_and_quota_protection(self):
        budget=self.client.budget
        budget.authenticated('a'*32)
        admission=budget.reserve('successful');budget.complete(admission);budget.success('successful',admission)
        budget.failure(wcl.APIError('WCL HTTP 429',429,50))
        budget.authenticated('b'*32)
        self.assertEqual(budget._value('profile:successful'),1300)
        with self.assertRaises(BudgetError) as caught:budget.reserve('new')
        self.assertEqual(caught.exception.code,'budget')

    def test_late_old_auth_failure_cannot_recreate_gate_after_relogin(self):
        budget=self.client.budget
        budget.authenticated('a'*32)
        admission=budget.reserve('old-auth')
        budget.complete(admission,sent=True,uncertain=True)
        budget.authenticated('b'*32)
        budget.failure(wcl.APIError('Old authentication failed',401),
                       'old-auth',admission,auth_generation='a'*32)
        self.assertLessEqual(budget._value('profile:old-auth'),self.now)
        self.assertEqual(budget._value('failure_count:old-auth'),0)

    def test_legacy_cache_migrates_once_without_sliding_deadline(self):
        builder.atomic_write(builder.cache_path(self.cache,self.entry),json.dumps(dict(fetched_at=0,
            retry_until=1300,refresh_error='Safe schema failure',error_code='schema')))
        self.build();self.assertEqual(self.cached()['retry_until'],1060)
        self.now=1005;self.build();self.assertEqual(self.cached()['retry_until'],1060)
        self.assertEqual(self.calls,[])
        self.now=1060;self.should_fail=False
        profiles,_=self.build();self.assertEqual(len(profiles),1)

    def test_legacy_failed_profile_admission_is_reconciled_to_migrated_cache(self):
        admission=self.client.budget.reserve(self.client.profile_key(builder.arguments(self.entry)))
        self.client.budget.complete(admission,sent=True,uncertain=True)
        builder.atomic_write(builder.cache_path(self.cache,self.entry),json.dumps(dict(fetched_at=0,
            retry_until=1300,refresh_error='Safe network failure',error_code='network')))
        self.build();self.assertEqual(self.cached()['retry_until'],1015)
        self.now=1015;self.should_fail=False
        profiles,report=self.build();self.assertEqual(len(profiles),1,report['errors'])

    def test_legacy_mislabelled_budget_cache_releases_old_failed_profile_gate(self):
        admission=self.client.budget.reserve(self.client.profile_key(builder.arguments(self.entry)))
        self.client.budget.complete(admission,sent=True,uncertain=True)
        builder.atomic_write(builder.cache_path(self.cache,self.entry),json.dumps(dict(fetched_at=0,
            retry_until=1300,refresh_error='WCL API budget is low',error_code='budget')))
        self.build();self.assertEqual(self.cached()['retry_until'],1015)
        self.assertEqual(self.cached()['error_code'],'retry')
        self.now=1015;self.should_fail=False
        profiles,report=self.build();self.assertEqual(len(profiles),1,report['errors'])

    def test_legacy_true_budget_cache_keeps_actual_reset(self):
        self.client.budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=3599,pointsResetIn=900))
        builder.atomic_write(builder.cache_path(self.cache,self.entry),json.dumps(dict(fetched_at=0,
            retry_until=1300,refresh_error='WCL API budget is low',error_code='budget')))
        self.build();self.assertEqual(self.cached()['retry_until'],1900)
        self.assertEqual(self.cached()['error_code'],'budget')
        self.assertEqual(self.calls,[])

    def test_legacy_true_short_quota_reset_also_shortens_owned_failed_gate(self):
        admission=self.client.budget.reserve(self.client.profile_key(builder.arguments(self.entry)))
        self.client.budget.complete(admission,sent=True,uncertain=True)
        self.client.budget.observe(dict(limitPerHour=3600,pointsSpentThisHour=3599,pointsResetIn=7))
        builder.atomic_write(builder.cache_path(self.cache,self.entry),json.dumps(dict(fetched_at=0,
            retry_until=1300,refresh_error='WCL API budget is low',error_code='budget')))
        self.build();self.assertEqual(self.cached()['retry_until'],1007)
        self.now=1007;self.should_fail=False
        profiles,report=self.build();self.assertEqual(len(profiles),1,report['errors'])

    def test_confirmed_budget_hint_is_not_downgraded_by_healthy_quota(self):
        calls=[]
        def fetch(args):
            calls.append(args.name)
            raise BudgetError('Local hourly query limit reached',720,retry_at=1720)
        fetch.budget=self.client.budget
        builder.build([self.entry],self.cache,fetcher=fetch,now=1000)
        self.assertEqual(self.cached()['retry_until'],1720)
        builder.build([self.entry],self.cache,fetcher=fetch,now=1001)
        builder.build([self.entry],self.cache,fetcher=fetch,now=1500)
        self.assertEqual(self.cached()['retry_until'],1720)
        self.assertEqual(self.cached()['error_code'],'budget')
        self.assertEqual(calls,['Alice'])

    def test_old_failure_cannot_shorten_a_newer_success_gate(self):
        budget=self.client.budget
        old=budget.reserve('same');budget.complete(old,sent=True,uncertain=True)
        self.now=1300
        newer=budget.reserve('same');budget.complete(newer);budget.success('same',newer)
        budget.failure(OSError('Late failure'),'same',old)
        self.assertEqual(budget._value('profile:same'),1600)

    def test_propagated_failure_does_not_advance_another_identity_streak(self):
        entries=[self.entry,dict(self.entry,name='Bob')]
        self.error=lambda:wcl.APIError('Safe network failure',code='network')
        builder.build(entries,self.cache,fetcher=self.client,now=self.now,max_workers=50)
        self.assertEqual(self.calls,['Alice'])
        bob=builder.read_cache(builder.cache_path(self.cache,entries[1]))
        self.assertEqual(bob['failure_count'],0)
        self.now=1015
        builder.build(entries[1:],self.cache,fetcher=self.client,now=self.now)
        bob=builder.read_cache(builder.cache_path(self.cache,entries[1]))
        self.assertEqual(bob['failure_count'],1)
        self.assertEqual(bob['retry_until'],1030)

if __name__=='__main__':unittest.main()
