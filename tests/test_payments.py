import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.database.models import Assignment, Payment
from bot.services.payments import create_payment


class FakeResult:
    def __init__(self, remaining):
        self.remaining = remaining

    def mappings(self):
        return self

    def first(self):
        return {"remaining_amount": self.remaining}


class FakeSession:
    def __init__(self, assignment=None, paid=Decimal("0"), existing=None):
        self.assignment = assignment
        self.paid = paid
        self.existing = existing
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.scalar_calls = 0

    async def scalar(self, statement):
        sql = str(statement).lower()
        self.scalar_calls += 1
        if "payments.operation_key" in sql:
            return self.existing
        if "assignments.id" in sql:
            return self.assignment
        if "sum(payments.amount)" in sql:
            return self.paid
        raise AssertionError(sql)

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, statement, params=None):
        remaining = self.assignment.commission_amount - self.paid
        return FakeResult(remaining)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def rollback(self):
        self.rollbacks += 1


def make_assignment(amount=Decimal("1000")):
    return SimpleNamespace(id=7, tutor_id=3, commission_amount=amount)


class PaymentServiceTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def create(self, session, amount=Decimal("300"), key="op-1"):
        return create_payment(session, 7, amount, key)

    def test_rejects_invalid_amount_without_database_calls(self):
        for amount in (0, Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.0):
            with self.subTest(amount=amount):
                session = FakeSession(assignment=make_assignment())
                with self.assertRaises(ValueError):
                    self.run_async(self.create(session, amount=amount))
                self.assertEqual(session.scalar_calls, 0)
                self.assertEqual(session.commits, 0)

    def test_partial_payment_is_saved_as_decimal(self):
        session = FakeSession(assignment=make_assignment(), paid=Decimal("250"))
        payment = Payment(assignment_id=7, amount=Decimal("300"), operation_key="allocation")
        batch = SimpleNamespace(id=4)
        with patch("bot.services.payments.create_tutor_payment_batch", new=AsyncMock(return_value=(batch, [payment]))) as create_batch:
            result = self.run_async(self.create(session))
        self.assertIs(result, payment)
        create_batch.assert_awaited_once()
        self.assertEqual(create_batch.await_args.kwargs["tutor_id"], 3)
        self.assertEqual(create_batch.await_args.kwargs["allocations"], [(7, Decimal("300"))])

    def test_overpayment_is_rejected_and_rolled_back(self):
        session = FakeSession(assignment=make_assignment(), paid=Decimal("900"))
        with patch("bot.services.payments.create_tutor_payment_batch", new=AsyncMock(side_effect=ValueError("превышает остаток"))):
            with self.assertRaisesRegex(ValueError, "превышает остаток"):
                self.run_async(self.create(session, amount=Decimal("101")))

    def test_repeated_operation_key_returns_existing_payment(self):
        prior = SimpleNamespace(id=15, assignment_id=7, amount=Decimal("300"))
        session = FakeSession(existing=prior)
        result = self.run_async(self.create(session))
        self.assertIs(result, prior)
        self.assertEqual(session.commits, 0)
        self.assertEqual(session.added, [])

    def test_reused_key_with_different_payment_is_rejected(self):
        prior = SimpleNamespace(id=15, assignment_id=7, amount=Decimal("300"))
        session = FakeSession(existing=prior)
        with self.assertRaisesRegex(ValueError, "другого платежа"):
            self.run_async(self.create(session, amount=Decimal("400")))
        self.assertEqual(session.commits, 0)


if __name__ == "__main__":
    unittest.main()
