import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

from bot.database.models import Assignment, Client, Lead, LeadSource, Tutor
from bot.services.assignments import create_assignment, create_manual_assignment


class FakeSession:
    def __init__(self, lead, tutor):
        self.lead = lead
        self.tutor = tutor
        self.client = SimpleNamespace(id=31, is_active=True)
        self.source = SimpleNamespace(id=42, is_active=True)
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
        if model is Client and object_id == self.client.id:
            return self.client
        if model is LeadSource and object_id == self.source.id:
            return self.source
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
    tutor = SimpleNamespace(id=53, is_active=True)
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

    def test_inactive_tutor_cannot_receive_assignment(self):
        session = make_session()
        session.tutor.is_active = False
        with self.assertRaisesRegex(ValueError, "Активный репетитор"):
            self.run_async(self.create(session))
        self.assertEqual(session.commits, 0)

    def test_archived_client_cannot_be_assigned(self):
        session = make_session()
        session.client.is_active = False
        with self.assertRaisesRegex(ValueError, "Ученик заявки"):
            self.run_async(self.create(session))
        self.assertEqual(session.commits, 0)

    def test_archived_source_cannot_be_assigned(self):
        session = make_session()
        session.source.is_active = False
        with self.assertRaisesRegex(ValueError, "Источник заявки"):
            self.run_async(self.create(session))
        self.assertEqual(session.commits, 0)

    def test_percent_mode_snapshots_the_rate_and_defers_amount_to_earnings(self):
        session = make_session()
        assignment = self.run_async(create_assignment(
            session, 17, 53, "Sonya", Decimal("1000"), "percent-op",
            commission_mode="percent", commission_percentage=Decimal("12.5"),
        ))
        self.assertEqual(assignment.commission_mode, "percent")
        self.assertEqual(assignment.commission_percentage, Decimal("12.5"))
        self.assertEqual(assignment.commission_amount, Decimal("0.00"))

    def test_percent_mode_rejects_invalid_percentage(self):
        session = make_session()
        with self.assertRaisesRegex(ValueError, "Процент комиссии"):
            self.run_async(create_assignment(
                session, 17, 53, "Sonya", Decimal("1000"), "bad-percent-op",
                commission_mode="percent", commission_percentage=Decimal("101"),
            ))
        self.assertEqual(session.commits, 0)

    def test_subscription_requires_purchase_date(self):
        session = make_session()
        with self.assertRaisesRegex(ValueError, "дату покупки"):
            self.run_async(create_assignment(
                session, 17, 53, "Sonya", Decimal("1000"), "subscription-op",
                commission_mode="subscription", commission_amount=Decimal("6000"),
            ))
        self.assertEqual(session.commits, 0)

    def test_fixed_mode_keeps_agreed_amount(self):
        session = make_session()
        assignment = self.run_async(create_assignment(
            session, 17, 53, "Sonya", Decimal("1000"), "fixed-op",
            commission_mode="fixed", commission_amount=Decimal("2750"),
        ))
        self.assertEqual(assignment.commission_mode, "fixed")
        self.assertEqual(assignment.commission_amount, Decimal("2750"))


class ManualAssignmentSession:
    """Small async-session fake for atomic manual entity creation tests."""
    def __init__(self):
        self.rows = {Tutor: [], Client: [], LeadSource: [], Lead: [], Assignment: []}
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.next_id = 1

    async def scalar(self, statement):
        sql = str(statement).lower()
        for model, table in ((Tutor, "tutors"), (Client, "clients"),
                             (LeadSource, "lead_sources"), (Lead, "leads"),
                             (Assignment, "assignments")):
            if f"from {table}" in sql:
                rows = self.rows[model]
                if model is Assignment:
                    return None
                if model is Lead and "where leads.id =" in sql:
                    return rows[0] if rows else None
                if model is Lead and "leads.client_id =" in sql:
                    return rows[0] if rows else None
                if rows:
                    return rows[0]
                return None
        raise AssertionError(sql)

    async def get(self, model, row_id):
        return next((row for row in self.rows.get(model, []) if row.id == row_id), None)

    def add(self, obj):
        self.added.append(obj)
        model = type(obj)
        if model in self.rows:
            if isinstance(obj, (Tutor, Client, LeadSource)):
                obj.is_active = True
            self.rows[model].append(obj)

    async def flush(self):
        for obj in self.added:
            if not hasattr(obj, "id") or getattr(obj, "id", None) is None:
                if isinstance(obj, (Tutor, Client, LeadSource, Lead)):
                    obj.id = self.next_id
                    self.next_id += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def rollback(self):
        self.rollbacks += 1


class ManualAssignmentTests(unittest.TestCase):
    def test_creates_missing_entities_and_assignment_in_one_commit(self):
        session = ManualAssignmentSession()
        assignment, created = asyncio.run(create_manual_assignment(
            session,
            tutor_name="  Anna  ", tutor_subject="Math",
            client_name="Misha", client_contact="parent@example.test",
            source_name="Recommendation", subject="Algebra",
            assigned_by="Sonya", rate=Decimal("1500"),
            commission_multiplier=Decimal("4"),
            commission_amount=Decimal("6000"), operation_key="manual-op-1",
        ))
        self.assertIsInstance(assignment, Assignment)
        self.assertEqual(created, {"tutor": True, "client": True, "source": True, "lead": True})
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.rollbacks, 0)
        self.assertEqual(len(session.rows[Tutor]), 1)
        self.assertEqual(len(session.rows[Client]), 1)
        self.assertEqual(len(session.rows[LeadSource]), 1)
        self.assertEqual(len(session.rows[Lead]), 1)
        self.assertEqual(session.rows[Lead][0].status, "assigned")

    def test_reuses_existing_active_entities_and_matching_lead(self):
        session = ManualAssignmentSession()
        tutor = Tutor(id=20, nickname="Anna", subject="Math", is_active=True)
        client = Client(id=21, nickname="Misha", contact="saved contact", is_active=True)
        source = LeadSource(id=22, name="Recommendation", is_active=True)
        lead = Lead(id=23, client_id=21, source_id=22, subject="Algebra", status="new")
        session.rows[Tutor].append(tutor)
        session.rows[Client].append(client)
        session.rows[LeadSource].append(source)
        session.rows[Lead].append(lead)
        assignment, created = asyncio.run(create_manual_assignment(
            session,
            tutor_name=" anna ", tutor_subject="Different value ignored",
            client_name="Misha", client_contact="new contact ignored",
            source_name="recommendation", subject="algebra",
            assigned_by="Sonya", rate=Decimal("1500"),
            commission_multiplier=Decimal("4"),
            commission_amount=Decimal("6000"), operation_key="manual-op-existing",
        ))
        self.assertEqual(created, {"tutor": False, "client": False, "source": False, "lead": False})
        self.assertEqual(client.contact, "saved contact")
        self.assertEqual(assignment.lead_id, lead.id)
        self.assertEqual(session.commits, 1)

    def test_invalid_input_rolls_back_and_creates_nothing(self):
        session = ManualAssignmentSession()
        with self.assertRaisesRegex(ValueError, "Имя ученика"):
            asyncio.run(create_manual_assignment(
                session,
                tutor_name="Anna", tutor_subject=None,
                client_name=" ", client_contact=None,
                source_name="Referral", subject=None,
                assigned_by="Sonya", rate=Decimal("1000"),
                commission_amount=Decimal("4000"), operation_key="manual-op-2",
            ))
        self.assertEqual(session.rollbacks, 0)
        self.assertEqual(session.commits, 0)


if __name__ == "__main__":
    unittest.main()
