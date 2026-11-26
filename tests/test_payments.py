import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

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
    return SimpleNamespace(id=7, commission_amount=amount)


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
        payment = self.run_async(self.create(session))
        self.assertIsInstance(payment, Payment)
        self.assertEqual(payment.amount, Decimal("300"))
        self.assertEqual(payment.operation_key, "op-1")
        self.assertEqual(session.commits, 1)

    def test_overpayment_is_rejected_and_rolled_back(self):
        session = FakeSession(assignment=make_assignment(), paid=Decimal("900"))
        with self.assertRaisesRegex(ValueError, "превышает остаток"):
            self.run_async(self.create(session, amount=Decimal("101")))
        self.assertEqual(session.commits, 0)
        self.assertEqual(session.rollbacks, 1)

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
