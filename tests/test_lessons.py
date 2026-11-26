import asyncio
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from bot.database.models import Assignment, Lesson
from bot.services.lessons import create_lesson


class FakeSession:
    def __init__(self, prior_paid_lessons=0, closed=False):
        self.prior_paid_lessons = prior_paid_lessons
        self.assignment = SimpleNamespace(
            id=7, is_closed=closed, short_term_lesson_limit=4, payment_due_date=None
        )
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, statement):
        sql = str(statement).lower()
        if "lessons.operation_key" in sql:
            return None
        if "count(lessons.id)" in sql:
            return self.prior_paid_lessons
        if "assignments.id" in sql:
            return self.assignment
        raise AssertionError(sql)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def rollback(self):
        self.rollbacks += 1


class LessonServiceTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def create(self, **kwargs):
        values = {
            "session": FakeSession(),
            "assignment_id": 7,
            "lesson_type": "paid",
            "status": "completed",
            "lesson_date": date(2026, 1, 5),
            "operation_key": "lesson-1",
            "amount": Decimal("1500"),
        }
        values.update(kwargs)
        return values["session"], create_lesson(**values)

    def test_paid_completed_lesson_requires_positive_decimal(self):
        for amount in (None, Decimal("0"), Decimal("-1"), Decimal("NaN"), 1500.0):
            with self.subTest(amount=amount):
                session, operation = self.create(amount=amount)
                with self.assertRaises(ValueError):
                    self.run_async(operation)
                self.assertEqual(session.commits, 0)

    def test_trial_lesson_does_not_accept_a_fee(self):
        session, operation = self.create(lesson_type="trial", amount=Decimal("10"))
        with self.assertRaisesRegex(ValueError, "Пробное"):
            self.run_async(operation)
        self.assertEqual(session.commits, 0)

    def test_cancelled_lesson_is_stored_without_money(self):
        session, operation = self.create(status="cancelled", amount=Decimal("1500"))
        lesson = self.run_async(operation)
        self.assertIsInstance(lesson, Lesson)
        self.assertIsNone(lesson.amount)
        self.assertEqual(lesson.status, "cancelled")
        self.assertEqual(session.commits, 1)

    def test_fourth_paid_lesson_sets_default_due_date(self):
        session, operation = self.create(session=FakeSession(prior_paid_lessons=3))
        self.run_async(operation)
        self.assertEqual(session.assignment.payment_due_date, date(2026, 1, 5))

    def test_closed_assignment_rejects_lesson(self):
        session, operation = self.create(session=FakeSession(closed=True))
        with self.assertRaisesRegex(ValueError, "закрытую"):
            self.run_async(operation)
        self.assertEqual(session.commits, 0)

    def test_completed_paid_lesson_is_saved(self):
        session, operation = self.create()
        lesson = self.run_async(operation)
        self.assertEqual(lesson.amount, Decimal("1500"))
        self.assertEqual(lesson.lesson_type, "paid")
        self.assertEqual(session.commits, 1)


if __name__ == "__main__":
    unittest.main()
