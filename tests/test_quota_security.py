"""Offline admission accounting; client-side budgets are not an abuse boundary."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from api_budget import Budget, BudgetError


def observation(spent=100, cost=10, reset=500):
    return dict(limitPerHour=1000, pointsSpentThisHour=spent,
                pointsResetIn=reset, currentRequest={"total": cost})


class QuotaSecurityTests(unittest.TestCase):
    def budget(self, **kwargs):
        budget = Budget(**kwargs)
        self.addCleanup(budget.close)
        return budget

    def test_parallel_reservations_stop_before_any_replies(self):
        budget = self.budget(hourly=1000, clock=lambda: 1000)
        budget.observe(observation(spent=800))
        def reserve(index):
            try:
                budget.reserve(str(index))
                return True
            except BudgetError:
                return False
        with ThreadPoolExecutor(max_workers=25) as pool:
            self.assertEqual(sum(pool.map(reserve, range(50))), 10)
        self.assertEqual(budget.snapshot()["projectedSpentThisHour"], 900)
        budget.check_upstream()  # Last admitted request still fits the reserve.

    def test_out_of_order_snapshots_never_release_local_reservations(self):
        budget = self.budget(clock=lambda: 1000)
        budget.observe(observation())
        for i in range(5):
            budget.reserve(str(i))
        for spent in (120, 160, 110):
            budget.observe(observation(spent))
        budget.success("0")
        self.assertEqual(budget.snapshot()["pointsSpentThisHour"], 160)
        self.assertEqual(budget.snapshot()["localReservedPoints"], 50)
        self.assertEqual(budget.snapshot()["projectedSpentThisHour"], 210)

    def test_failed_attempts_and_restart_keep_point_reservations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            budget = Budget(path, clock=lambda: 1000)
            budget.observe(observation())
            budget.reserve("one")
            budget.failure(ValueError("transport failed"))
            budget.close()
            restored = Budget(path, clock=lambda: 1000)
            try:
                self.assertEqual(restored.snapshot()["localReservedPoints"], 10)
            finally:
                restored.close()

    def test_learning_a_larger_cost_revalues_already_sent_work(self):
        budget = self.budget(clock=lambda: 1000)
        budget.reserve("unknown")
        budget.reserve("also-unknown")
        budget.observe(observation(spent=1, cost=10.02))
        self.assertAlmostEqual(budget.snapshot()["projectedSpentThisHour"], 21.04)
        budget.observe(observation(spent=1, cost=20))
        self.assertEqual(budget.snapshot()["localReservedPoints"], 40)

    def test_reservations_expire_without_requiring_a_new_reserve(self):
        stamp = [1000]
        budget = self.budget(clock=lambda: stamp[0])
        budget.observe(observation())
        budget.reserve("one")
        stamp[0] += 3600
        self.assertEqual(budget.snapshot()["localReservedPoints"], 0)
        budget.reserve("two")

    def test_quota_reset_does_not_reprice_unsettled_old_work_down(self):
        stamp = [1000]
        budget = self.budget(clock=lambda: stamp[0])
        budget.observe(observation(reset=100))
        budget.reserve("old")
        stamp[0] += 101
        budget.observe(observation(spent=1, cost=1))
        self.assertEqual(budget.snapshot()["localReservedPoints"], 10)

    def test_two_connections_cannot_overbook_the_same_point_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            budgets = [Budget(path, clock=lambda: 1000) for _ in range(2)]
            try:
                budgets[0].observe(observation(spent=880))
                budgets[0].reserve("a")
                budgets[1].reserve("b")
                with self.assertRaises(BudgetError):
                    budgets[0].reserve("c")
                self.assertEqual(budgets[1].snapshot()["projectedSpentThisHour"], 900)
            finally:
                for budget in budgets:
                    budget.close()


if __name__ == "__main__":
    unittest.main()
