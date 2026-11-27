import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

from bot.database.models import AssignmentAdjustment, CommissionAccrual
from bot.services.finance import close_assignment, short_term_commission


class ShortTermCommissionTests(unittest.TestCase):
    def test_up_to_four_paid_lessons_uses_25_percent_of_actual_earnings(self):
        applies, amount = short_term_commission(Decimal("8000"), 4)
        self.assertTrue(applies)
        self.assertEqual(amount, Decimal("2000.00"))

    def test_short_term_calculation_rounds_currency_to_cents(self):
        applies, amount = short_term_commission(Decimal("100.10"), 1)
        self.assertTrue(applies)
        self.assertEqual(amount, Decimal("25.03"))

    def test_more_than_four_lessons_keeps_long_term_commission(self):
        applies, amount = short_term_commission(Decimal("10000"), 5)
        self.assertFalse(applies)
        self.assertEqual(amount, Decimal("0.00"))

    def test_invalid_earnings_and_threshold_are_rejected(self):
        with self.assertRaises(ValueError):
            short_term_commission(Decimal("NaN"), 1)
        with self.assertRaises(ValueError):
            short_term_commission(Decimal("10"), 1, 0)


class FakeStats:
    def __init__(self, count, earnings):
        self.values = (count, earnings)

    def one(self):
        return self.values


class FakeCloseSession:
    def __init__(self, lesson_count, earnings):
        self.assignment = SimpleNamespace(
            id=9,
            commission_amount=Decimal("4000"),
            short_term_lesson_limit=4,
            is_closed=False,
            close_operation_key=None,
            close_reason=None,
            closed_by=None,
            payment_due_date=None,
            commission_mode="rate_multiplier",
            commission_percentage=None,
        )
        self.lesson_count = lesson_count
        self.earnings = earnings
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.scalar_calls = 0

    async def scalar(self, statement):
        self.scalar_calls += 1
        if self.scalar_calls == 2:
            return self.assignment
        return None

    async def execute(self, statement):
        return FakeStats(self.lesson_count, self.earnings)

    def add(self, record):
        self.added.append(record)

    async def commit(self):
        self.commits += 1

    async def refresh(self, record):
        return None

    async def rollback(self):
        self.rollbacks += 1


class CloseAssignmentTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_short_assignment_close_appends_25_percent_adjustment(self):
        session = FakeCloseSession(3, Decimal("4000"))
        assignment, adjustment = self.run_async(close_assignment(
            session, 9, "Занятия завершены", "Sonya", "close-9"
        ))
        self.assertTrue(assignment.is_closed)
        self.assertIsInstance(adjustment, AssignmentAdjustment)
        self.assertEqual(adjustment.previous_amount, Decimal("4000"))
        self.assertEqual(adjustment.new_amount, Decimal("1000.00"))
        self.assertEqual(adjustment.difference, Decimal("-3000.00"))
        self.assertEqual(session.commits, 1)

    def test_long_assignment_close_keeps_agreed_commission(self):
        session = FakeCloseSession(5, Decimal("9000"))
        assignment, adjustment = self.run_async(close_assignment(
            session, 9, "Обучение завершено", "Sonya", "close-10"
        ))
        self.assertTrue(assignment.is_closed)
        self.assertIsNone(adjustment)
        self.assertEqual(assignment.commission_amount, Decimal("4000"))
        self.assertEqual(session.commits, 1)

    def test_closure_requires_reason_and_author(self):
        session = FakeCloseSession(2, Decimal("2000"))
        with self.assertRaises(ValueError):
            self.run_async(close_assignment(session, 9, "", "Sonya", "close-11"))
        with self.assertRaises(ValueError):
            self.run_async(close_assignment(session, 9, "reason", "", "close-12"))
        self.assertEqual(session.commits, 0)

    def test_percent_commission_settles_from_actual_paid_earnings(self):
        session = FakeCloseSession(2, Decimal("2000"))
        session.assignment.commission_mode = "percent"
        session.assignment.commission_percentage = Decimal("10")
        session.assignment.commission_amount = Decimal("0")
        _, adjustment = self.run_async(close_assignment(
            session, 9, "Завершено", "Sonya", "percent-close-1"
        ))
        self.assertEqual(adjustment.new_amount, Decimal("200.00"))

    def test_subscription_preserves_the_pre_agreed_commission_on_close(self):
        session = FakeCloseSession(2, Decimal("2000"))
        session.assignment.commission_mode = "subscription"
        _, adjustment = self.run_async(close_assignment(
            session, 9, "Завершено", "Sonya", "subscription-close-1"
        ))
        self.assertIsNone(adjustment)

    def test_fixed_commission_is_accrued_when_closed_before_threshold(self):
        session = FakeCloseSession(2, Decimal("2000"))
        session.assignment.commission_mode = "fixed"
        _, adjustment = self.run_async(close_assignment(
            session, 9, "Завершено", "Sonya", "fixed-close-1"
        ))
        self.assertIsNone(adjustment)
        accrual = next(item for item in session.added if isinstance(item, CommissionAccrual))
        self.assertEqual((accrual.event_type, accrual.amount), ("closure", Decimal("4000")))


if __name__ == "__main__":
    unittest.main()
