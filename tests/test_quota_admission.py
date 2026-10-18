"""Regression: completed legacy attempts must not block a healthy WCL quota."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from api_budget import Budget
from api_budget import BudgetError
import clipboard_companion as bridge
import build_database as builder


def quota(spent=0,cost=10.02,cap=3600):
    result=dict(limitPerHour=cap,pointsSpentThisHour=spent,pointsResetIn=3600)
    if cost is not None:result['currentRequest']={'total':cost}
    return result


class QuotaAdmissionTests(unittest.TestCase):
    def budget(self):
        budget=Budget(clock=lambda:1000)
        self.addCleanup(budget.close)
        return budget

    def test_legacy_history_502_of_3600_allows_loading(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            path=Path(directory)/'state.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE attempts (at REAL NOT NULL,key TEXT NOT NULL)')
                db.execute('CREATE TABLE state (key TEXT PRIMARY KEY,value REAL NOT NULL)')
                db.executemany('INSERT INTO attempts VALUES (?,?)',[(1000,str(i)) for i in range(164)])
                db.executemany('INSERT INTO state VALUES (?,?)',[
                    ('limit',3600),('spent',502),('reset_at',3500),('largest_observed_cost',163.36)])
            db.close()
            budget=Budget(path,hourly=3600,clock=lambda:1001)
            try:
                budget.check_upstream()
                self.assertEqual(budget.snapshot()['projectedSpentThisHour'],502)
                self.assertEqual(budget.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],164)
            finally:budget.close()

    def test_completed_wave_costs_reconcile_with_later_quota_snapshot(self):
        budget=self.budget();budget.observe(quota())
        admissions=[budget.reserve(str(i)) for i in range(50)]
        for i,admission in enumerate(admissions):
            budget.complete(admission,quota(min(338.64,i*10.02)))
        self.assertAlmostEqual(budget.snapshot()['projectedSpentThisHour'],501)
        self.assertEqual(budget.snapshot()['localReservedPoints'],0)
        budget.observe(quota(501))
        self.assertAlmostEqual(budget.snapshot()['projectedSpentThisHour'],501)
        budget.observe(quota(501,100))
        self.assertAlmostEqual(budget.snapshot()['projectedSpentThisHour'],501)

    def test_quota_only_snapshot_cannot_become_one_request_price(self):
        budget=self.budget();budget.observe(quota(338.64))
        budget.observe(quota(502,None))
        self.assertAlmostEqual(budget.snapshot()['requestCostEstimate'],10.02)

    def test_last_fit_query_is_sent_once_and_result_is_returned(self):
        client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(client.budget.close)
        client.budget.observe(quota(890,10,1000))
        calls=[]
        raw={'data':{'rateLimitData':quota(890,10,1000)}}
        result=client._query('last-fit',lambda token:calls.append(token) or raw)
        self.assertIs(result,raw)
        self.assertEqual(calls,['fixture'])
        self.assertEqual(client.budget.snapshot()['localReservedPoints'],0)
        with self.assertRaises(BudgetError):
            client._query('no-room',lambda token:self.fail('Blocked query must not reach WCL'))

    def test_cancel_before_send_releases_points_but_keeps_attempt_history(self):
        client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(client.budget.close)
        client.cancel=threading.Event();client.cancel.set()
        client.budget.observe(quota(100))
        with self.assertRaises(ValueError):
            client._query('cancelled',lambda token:self.fail('Cancelled query must not reach WCL'))
        self.assertEqual(client.budget.snapshot()['localReservedPoints'],0)
        self.assertEqual(client.budget.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1)

    def test_network_error_keeps_only_its_uncertain_cost(self):
        client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(client.budget.close)
        client.budget.observe(quota(100,10))
        def fail(token):raise OSError('network timeout')
        with self.assertRaises(OSError):client._query('timeout',fail)
        self.assertEqual(client.budget.snapshot()['localReservedPoints'],10)
        self.assertEqual(client.budget.snapshot()['projectedSpentThisHour'],110)

    def test_api_error_with_known_cost_is_settled_without_double_counting(self):
        client=bridge.Client(token_provider=lambda:'fixture')
        self.addCleanup(client.budget.close)
        client.budget.observe(quota(100,10))
        def fail(token):raise bridge.wcl.APIError('GraphQL error',rate_limit=quota(110,10))
        with self.assertRaises(ValueError):client._query('known-error',fail)
        client.budget.observe(quota(110,10))
        self.assertEqual(client.budget.snapshot()['localReservedPoints'],0)
        self.assertEqual(client.budget.snapshot()['projectedSpentThisHour'],110)

    def test_first_response_may_already_include_its_cost(self):
        budget=self.budget()
        admission=budget.reserve('first')
        budget.complete(admission,quota(110,10))
        self.assertEqual(budget.snapshot()['projectedSpentThisHour'],110)

    def test_old_cached_budget_failure_is_rechecked_before_waiting(self):
        budget=self.budget();budget.observe(quota(502))
        fetch=lambda args:None
        fetch.budget=budget
        cached=dict(retry_until=3500,refresh_error='WCL API budget is low',error_code='budget')
        self.assertFalse(builder._retry_cache_active(cached,1000,fetch))
        budget.failure(bridge.wcl.APIError('WCL HTTP 429',429,300))
        self.assertTrue(builder._retry_cache_active(cached,1000,fetch))


if __name__=='__main__':unittest.main()
