"""GraphQL failure isolation, safe diagnostics and truthful retry metadata."""
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from test_addon import ROOT, api_fixture
import wcl_sync as wcl
import build_database as builder
import clipboard_companion as bridge
from api_budget import Budget, BudgetError


class GraphQLFailureTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix='.test-graphql-',dir=ROOT)
        self.addCleanup(folder.cleanup)
        self.cache=Path(folder.name)
        self.entries=[dict(name=name,realm='Гордунни',server_slug='gordunni',region='eu') for name in ('Alice','Bob','Carol')]

    def error(self, errors):
        args=builder.arguments(self.entries[0])
        with patch.object(wcl,'request_json',return_value={'errors':errors}):
            with self.assertRaises(wcl.APIError) as caught:wcl.fetch(args,'test-token')
        return caught.exception

    def raw(self,args):
        raw=copy.deepcopy(api_fixture())
        raw['data']['characterData']['character']['name']=args.name
        return raw

    def test_known_graphql_codes_are_classified_without_raw_messages(self):
        for upstream,code in [('RATE_LIMITED','budget'),('UNAUTHENTICATED','auth'),('GRAPHQL_VALIDATION_FAILED','schema')]:
            with self.subTest(upstream=upstream):
                error=self.error([{'message':'secret-token='+('x'*1000),'extensions':{'code':upstream}}])
                self.assertEqual(error.code,code)
                self.assertIn(upstream,str(error))
                self.assertNotIn('secret-token',str(error))
                self.assertLess(len(str(error)),400)

    def test_known_validation_field_is_retained_without_suggestions_or_values(self):
        error=self.error([{'message':'Cannot query field "currentRequest" on type "RateLimitData". Did you mean secretToken?',
                           'extensions':{'code':'GRAPHQL_VALIDATION_FAILED'}}])
        self.assertIn('currentRequest',str(error))
        self.assertNotIn('secretToken',str(error))

    def test_malicious_diagnostic_metadata_is_not_echoed(self):
        secret='BearerSecret123'
        error=self.error([{'message':secret,'path':['characterData','character',secret],
                           'extensions':{'code':secret,'exception':{'token':secret}}}])
        self.assertNotIn(secret,str(error))
        self.assertIn('characterData.character',str(error))
        self.assertEqual(error.code,'retry')
        self.assertFalse(error.global_stop)

    def test_common_errors_without_extensions_are_classified(self):
        for message,code in [('Rate limit exceeded.','budget'),('Unauthenticated.','auth')]:
            with self.subTest(message=message):self.assertEqual(self.error([{'message':message}]).code,code)

    def test_mixed_local_and_systemic_errors_keep_global_stop(self):
        error=self.error([{'path':['characterData','character','damage']},
                          {'extensions':{'code':'UNAUTHENTICATED'}}])
        self.assertEqual(error.code,'auth')
        self.assertTrue(error.global_stop)

    def test_truncated_error_list_cannot_hide_a_systemic_error(self):
        errors=[{'path':['characterData','character','damage']}] * 8
        error=self.error(errors+[{'extensions':{'code':'UNAUTHENTICATED'}}])
        self.assertTrue(error.global_stop)

    def test_mixed_local_absence_and_transient_failure_remains_retryable(self):
        error=self.error([{'path':['characterData','character'],'extensions':{'code':'FORBIDDEN'}},
                          {'path':['characterData','character','damage']}])
        self.assertEqual(error.code,'retry')
        self.assertFalse(error.global_stop)

    def test_local_character_failure_does_not_abort_others(self):
        for workers in (1,50):
            with self.subTest(workers=workers):
                calls=[]
                def fetch(args):
                    calls.append(args.name)
                    if args.name=='Alice':raise self.error([{'message':'Internal server error','path':['characterData','character','damage']}])
                    return self.raw(args)
                profiles,report=builder.build(self.entries,self.cache/str(workers),fetcher=fetch,max_workers=workers,now=1000)
                self.assertEqual([p['name'] for p in profiles],['Bob','Carol'])
                self.assertEqual(len(calls),3)
                self.assertEqual(len(report['errors']),1)

    def test_systemic_query_error_still_stops_whole_batch(self):
        calls=[]
        def fetch(args):
            calls.append(args.name)
            raise self.error([{'message':'Cannot query field "currentRequest" on type "RateLimitData".',
                               'extensions':{'code':'GRAPHQL_VALIDATION_FAILED'}}])
        _,report=builder.build(self.entries,self.cache,fetcher=fetch,max_workers=50,now=1000)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(report['errors']),3)
        self.assertTrue(all(row['retry_at']==1060 for row in report['errors']))

    def test_retry_metadata_matches_actual_cache_gate_on_first_and_repeat(self):
        calls=[]
        def fetch(args):calls.append(args.name);raise wcl.APIError('Safe upstream failure',code='schema')
        _,first=builder.build(self.entries[:1],self.cache,fetcher=fetch,now=1000)
        _,second=builder.build(self.entries[:1],self.cache,fetcher=fetch,now=1001)
        self.assertEqual(first['errors'][0]['retry_at'],1060)
        self.assertEqual(second['errors'][0]['retry_at'],1060)
        self.assertEqual(len(calls),1)
        builder.build(self.entries[:1],self.cache,fetcher=fetch,now=1060)
        self.assertEqual(len(calls),2)

    def test_absolute_retry_deadline_is_honored(self):
        def fetch(args):raise wcl.ProfileError('Try later','retry',2000)
        _,report=builder.build(self.entries[:1],self.cache,fetcher=fetch,now=1000)
        self.assertEqual(report['errors'][0]['retry_at'],2000)
        cached=builder.read_cache(builder.cache_path(self.cache,self.entries[0]))
        self.assertEqual(cached['retry_until'],2000)

    def test_fractional_clock_cannot_advertise_before_cache_gate(self):
        def fetch(args):raise wcl.APIError('Safe upstream failure',code='schema')
        _,report=builder.build(self.entries[:1],self.cache,fetcher=fetch,now=1000.75)
        cached=builder.read_cache(builder.cache_path(self.cache,self.entries[0]))
        self.assertEqual(report['errors'][0]['retry_at'],1061)
        self.assertEqual(cached['retry_until'],1061)

    def budget(self):
        budget=Budget(clock=lambda:1000)
        self.addCleanup(budget.close)
        budget.observe(dict(limitPerHour=36000,pointsSpentThisHour=10,pointsResetIn=1000))
        return budget

    def test_schema_pause_is_retry_not_low_budget(self):
        budget=self.budget();budget.failure(wcl.APIError('Safe schema failure',code='schema'))
        with self.assertRaises(BudgetError) as caught:budget.check_upstream()
        self.assertEqual(caught.exception.code,'retry')
        self.assertNotIn('budget is low',str(caught.exception))
        self.assertEqual(caught.exception.retry_after,60)

    def test_zero_parallel_slots_preserve_actual_generic_pause_reason(self):
        class PausedClient(bridge.Client):
            def parallel_capacity(self, remaining):
                self.budget.failure(wcl.APIError('Safe schema failure',code='schema'))
                return super().parallel_capacity(remaining)
        client=PausedClient(token_provider=lambda:'test-token')
        self.addCleanup(client.budget.close)
        client.budget.observe(dict(limitPerHour=36000,pointsSpentThisHour=10,pointsResetIn=3600))
        now=time.time()
        with patch.object(wcl,'fetch',side_effect=lambda args,*a,**k:self.raw(args)) as fetch:
            profiles,report=builder.build(self.entries,self.cache,fetcher=client,max_workers=50,now=now)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(len(profiles),1)
        self.assertEqual(len(report['errors']),2)
        for error in report['errors']:
            self.assertEqual(error['error_code'],'retry')
            self.assertNotIn('budget is low',error['error'])
            self.assertLess(error['retry_at'],now+3600)
            self.assertGreaterEqual(error['retry_at'],now+60)

    def test_local_error_does_not_pause_other_identities(self):
        budget=self.budget()
        error=self.error([{'message':'Internal server error','path':['characterData','character']}])
        budget.failure(error)
        budget.check_upstream()
        self.assertEqual(budget.snapshot()['blockedUntil'],0)

    def test_real_rate_limit_remains_budget_with_reset_protection(self):
        budget=self.budget();budget.failure(wcl.APIError('WCL HTTP 429',429,20))
        with self.assertRaises(BudgetError) as caught:budget.check_upstream()
        self.assertEqual(caught.exception.code,'budget')
        self.assertEqual(caught.exception.retry_after,1000)

    def test_legacy_unattributed_global_pause_keeps_protection_without_false_quota_claim(self):
        budget=self.budget()
        with budget.db:budget._set('blocked_until',1060)
        with self.assertRaises(BudgetError) as caught:budget.check_upstream()
        self.assertEqual(caught.exception.code,'retry')
        self.assertEqual(caught.exception.retry_after,60)

    def test_legacy_cached_budget_error_uses_current_retry_reason(self):
        budget=self.budget()
        with budget.db:budget._set('blocked_until',1060)
        def fetch(args):self.fail('The legacy pause must still block network')
        fetch.budget=budget
        path=builder.cache_path(self.cache,self.entries[0])
        builder.atomic_write(path,json.dumps(dict(fetched_at=0,retry_until=1300,
            refresh_error='WCL API budget is low',error_code='budget')))
        _,report=builder.build(self.entries[:1],self.cache,fetcher=fetch,now=1000)
        self.assertEqual(report['errors'][0]['error_code'],'retry')
        self.assertNotIn('budget is low',report['errors'][0]['error'])

if __name__=='__main__':unittest.main()
