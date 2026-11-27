import asyncio
import unittest
from types import SimpleNamespace

from bot.database.models import LeadStatusHistory
from bot.services.leads import record_lead_status_change, update_lead_status


class FakeSession:
    def __init__(self, lead):
        self.lead = lead
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, statement):
        self.assert_lead_query = "leads.id" in str(statement)
        return self.lead if self.assert_lead_query else None

    async def get(self, model, object_id):
        return self.lead if object_id == self.lead.id else None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    async def rollback(self):
        self.rollbacks += 1


def session(status="new", reason=None):
    return FakeSession(SimpleNamespace(id=7, status=status, lost_reason=reason))


class LeadStatusTests(unittest.TestCase):
    def run_async(self, awaitable):
        return asyncio.run(awaitable)

    def test_valid_transition_appends_history(self):
        db = session()
        result = self.run_async(update_lead_status(db, 7, "in_progress", changed_by="Sonya"))
        self.assertEqual(result.status, "in_progress")
        self.assertEqual(db.commits, 1)
        event = next(item for item in db.added if isinstance(item, LeadStatusHistory))
        self.assertEqual((event.old_status, event.new_status, event.changed_by), ("new", "in_progress", "Sonya"))

    def test_lost_requires_reason(self):
        db = session()
        with self.assertRaisesRegex(ValueError, "причину"):
            self.run_async(update_lead_status(db, 7, "lost"))
        self.assertEqual(db.commits, 0)

    def test_invalid_transition_is_rejected(self):
        db = session("lost", "не подошли условия")
        with self.assertRaisesRegex(ValueError, "при создании передачи"):
            self.run_async(update_lead_status(db, 7, "assigned"))
        self.assertEqual(db.commits, 0)

    def test_lost_lead_can_be_reopened_with_reason_in_history(self):
        db = session("lost", "не подошли условия")
        self.run_async(update_lead_status(db, 7, "in_progress", changed_by="Sonya", reason="клиент вернулся"))
        event = next(item for item in db.added if isinstance(item, LeadStatusHistory))
        self.assertEqual(event.reason, "клиент вернулся")
        self.assertIsNone(db.lead.lost_reason)

    def test_assignment_transition_helper_preserves_transaction_boundary(self):
        db = session("in_progress")
        record_lead_status_change(db, db.lead, "assigned", changed_by="Sonya", reason="передача")
        self.assertEqual(db.lead.status, "assigned")
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.added[0].new_status, "assigned")


if __name__ == "__main__":
    unittest.main()
