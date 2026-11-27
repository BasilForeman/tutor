import unittest
from datetime import date
from decimal import Decimal

from bot.services.analytics import format_analytics, get_analytics, period_bounds


class FakeResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one(self):
        return self.value

    def all(self):
        return self.value


class FakeSession:
    def __init__(self, results):
        self.results = iter(results)
        self.statements = []

    async def execute(self, statement, params):
        self.statements.append((str(statement), params))
        return FakeResult(next(self.results))


class AnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_period_and_aggregates_are_combined(self):
        session = FakeSession([
            {"leads": 4, "converted_leads": 1, "assignments": 2,
             "active_assignments": 1, "closed_assignments": 1,
             "completed_lessons": 7, "trial_lessons": 1, "paid_lessons": 6,
             "cancelled_lessons": 2, "earnings": Decimal("900"),
             "payments": Decimal("500"), "refunds": Decimal("100"),
             "commission_accrued": Decimal("250"), "current_debt": Decimal("350"),
             "debtor_tutors": 1, "average_tutor_debt": Decimal("350"),
             "refund_count": 1},
            [{"source_id": 1, "source": "Referral", "leads": 4,
              "assignments": 2, "converted_leads": 1,
              "conversion_percent": Decimal("25.00")}],
            [{"tutor_id": 8, "tutor": "Tutor", "assignments": 2,
              "active_assignments": 1, "closed_assignments": 1,
              "completed_lessons": 7, "trial_lessons": 1, "paid_lessons": 6,
              "earnings": Decimal("900"), "commission_accrued": Decimal("250"),
              "net_payments": Decimal("400"), "refund_count": 1,
              "current_debt": Decimal("350")}],
            [{"tutor_id": 8, "tutor": "Tutor", "current_debt": Decimal("350")}],
            [{"day": date(2026, 11, 27), "transfers": 1, "lessons": 2,
              "net_payments": Decimal("100"), "commission_accrued": Decimal("50")}],
        ])
        report = await get_analytics(session, date(2026, 11, 1), date(2026, 11, 27))
        self.assertEqual(report["conversion_percent"], Decimal("25.00"))
        self.assertEqual(report["net_payments"], Decimal("400"))
        self.assertEqual(report["period"], (date(2026, 11, 1), date(2026, 11, 27)))
        self.assertEqual(report["sources"][0]["conversion_percent"], Decimal("25.00"))
        self.assertEqual(report["daily"][0]["transfers"], 1)
        self.assertEqual(report["debtors"][0]["current_debt"], Decimal("350"))
        self.assertEqual(len(session.statements), 5)

    async def test_invalid_period_is_rejected_before_query(self):
        session = FakeSession([])
        with self.assertRaises(ValueError):
            await get_analytics(session, date(2026, 11, 27), date(2026, 11, 1))
        self.assertEqual(session.statements, [])

    def test_preset_date_bounds(self):
        today = date(2026, 11, 27)
        self.assertEqual(period_bounds("today", today), (today, today))
        self.assertEqual(period_bounds("7d", today), (date(2026, 11, 21), today))
        self.assertEqual(period_bounds("month", today), (date(2026, 11, 1), today))
        self.assertEqual(period_bounds("previous_month", today),
                         (date(2026, 10, 1), date(2026, 10, 31)))
        with self.assertRaises(ValueError):
            period_bounds("all", today)

    def test_report_separates_period_events_from_current_debt(self):
        report = {
            "period": (date(2026, 11, 1), date(2026, 11, 27)), "leads": 4,
            "assignments": 2, "converted_leads": 1,
            "conversion_percent": Decimal("25.00"), "active_assignments": 1,
            "closed_assignments": 1, "completed_lessons": 4, "trial_lessons": 1,
            "paid_lessons": 3, "cancelled_lessons": 0,
            "earnings": Decimal("450"), "commission_accrued": Decimal("120"),
            "net_payments": Decimal("200"), "payments": Decimal("250"),
            "refunds": Decimal("50"), "refund_count": 1,
            "current_debt": Decimal("900"), "debtor_tutors": 2,
            "average_tutor_debt": Decimal("450"),
            "sources": [{"source": "Referral", "leads": 2, "assignments": 1,
                         "converted_leads": 1, "conversion_percent": Decimal("50.00")}],
            "tutors": [{"tutor": "Tutor", "assignments": 2,
                        "completed_lessons": 4, "commission_accrued": Decimal("120"),
                        "net_payments": Decimal("200"), "current_debt": Decimal("900")}],
            "debtors": [{"tutor": "Tutor", "current_debt": Decimal("900")}],
            "daily": [{"day": date(2026, 11, 27), "transfers": 1, "lessons": 2,
                       "net_payments": Decimal("200"), "commission_accrued": Decimal("120")}],
        }
        output = format_analytics(report)
        self.assertIn("Платежи получены: 250.00", output)
        self.assertIn("нетто: 200.00", output)
        self.assertIn("Текущий долг: 900.00", output)
        self.assertIn("Referral: 2 / 1 / 50.00%", output)
        self.assertIn("Динамика", output)
        self.assertIn("Крупнейшие текущие долги", output)
        self.assertIn("выплаты нетто", output)


if __name__ == "__main__":
    unittest.main()
