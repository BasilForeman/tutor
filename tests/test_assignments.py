import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

from bot.database.models import Assignment, Lead, Tutor
from bot.services.assignments import create_assignment


class FakeSession:
    def __init__(self, lead, tutor):
        self.lead = lead
        self.tutor = tutor
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.scalar_calls = 0
        self.existing = None

    async def scalar(self, statement):
        sql = str(statement).lower()
        self.scalar_calls += 1
        if "assignments.operation_key" in sql:
            return self.existing
        if "leads.id" in sql:
            return self.lead
        raise AssertionError(sql)

    async def get(self, model, object_id):
        if model is Lead and object_id == self.lead.id:
            return self.lead
        if model is Tutor and object_id == self.tutor.id:
            return self.tutor
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def rollback(self):
        self.rollbacks += 1


def make_session(status="new"):
    lead = SimpleNamespace(
        id=17, status=status, client_id=31, source_id=42
    )
    tutor = SimpleNamespace(id=53)
    return FakeSession(lead, tutor)


class AssignmentServiceTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def create(self, session, rate=Decimal("1000"), commission=Decimal("4000"), multiplier=Decimal("4")):
        return create_assignment(
            session=session,
            lead_id=17,
            tutor_id=53,
            assigned_by="Sonya",
            rate=rate,
            commission_amount=commission,
            commission_multiplier=multiplier,
            operation_key="assignment-op-1",
        )

    def test_rejects_non_decimal_or_non_finite_money(self):
        for value in (1000.0, Decimal("NaN"), Decimal("Infinity"), Decimal("0")):
            with self.subTest(value=value):
                session = make_session()
                with self.assertRaises(ValueError):
                    self.run_async(self.create(session, rate=value))
                self.assertEqual(session.commits, 0)

        for value in (4000.0, Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01")):
            with self.subTest(value=value):
                session = make_session()
                with self.assertRaises(ValueError):
                    self.run_async(self.create(session, commission=value))
                self.assertEqual(session.commits, 0)

    def test_repeated_assignment_creates_a_separate_record(self):
        session = make_session(status="assigned")
        assignment = self.run_async(self.create(session))
        self.assertIsInstance(assignment, Assignment)
        self.assertEqual(assignment.lead_id, session.lead.id)
        self.assertEqual(assignment.client_id, session.lead.client_id)
        self.assertEqual(assignment.source_id, session.lead.source_id)
        self.assertEqual(session.commits, 1)

    def test_repeated_operation_key_returns_the_existing_assignment(self):
        session = make_session()
        prior = SimpleNamespace(
            id=81, lead_id=17, tutor_id=53,
            rate=Decimal("1000"), commission_amount=Decimal("4000"),
            commission_multiplier=Decimal("4"), assigned_by="Sonya",
            assignment_date=None, payment_due_date=None,
        )
        session.existing = prior
        result = self.run_async(self.create(session))
        self.assertIs(result, prior)
        self.assertEqual(session.commits, 0)

    def test_reused_operation_key_with_different_values_is_rejected(self):
        session = make_session()
        session.existing = SimpleNamespace(
            id=81, lead_id=17, tutor_id=53,
            rate=Decimal("1000"), commission_amount=Decimal("4000"),
            commission_multiplier=Decimal("4"), assigned_by="Sonya",
            assignment_date=None, payment_due_date=None,
        )
        with self.assertRaisesRegex(ValueError, "другой передачи"):
            self.run_async(self.create(
                session, commission=Decimal("4500"), multiplier=Decimal("4.5")
            ))
        self.assertEqual(session.commits, 0)

    def test_lost_lead_cannot_be_assigned(self):
        session = make_session(status="lost")
        with self.assertRaisesRegex(ValueError, "потерянную"):
            self.run_async(self.create(session))
        self.assertEqual(session.commits, 0)


if __name__ == "__main__":
    unittest.main()
