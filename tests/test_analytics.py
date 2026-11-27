import unittest
from datetime import date
from decimal import Decimal

from bot.services.analytics import format_analytics, get_analytics


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

    async def execute(self, statement, params):
        return FakeResult(next(self.results))


class AnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_period_and_aggregates_are_combined(self):
        session = FakeSession([
            {"leads": 4, "converted_leads": 1, "assignments": 2,
             "completed_paid_lessons": 6, "earnings": Decimal("900"),
             "payments": Decimal("500"), "refunds": Decimal("100"),
             "overdue_assignments": 1, "overdue_amount": Decimal("250")},
            [{"source_id": 1, "source": "Referral", "leads": 4,
              "converted_leads": 1, "conversion_percent": Decimal("25.00")}],
            [{"month": "2026-11", "paid_lessons": 6, "earnings": Decimal("900")}],
            [{"tutor_id": 8, "tutor": "Tutor", "completed_paid_lessons": 6,
              "earnings": Decimal("900")}],
        ])
        report = await get_analytics(session, date(2026, 11, 1), date(2026, 11, 27))
        self.assertEqual(report["conversion_percent"], Decimal("25.00"))
        self.assertEqual(report["net_payments"], Decimal("400"))
        self.assertEqual(report["period"], (date(2026, 11, 1), date(2026, 11, 27)))
        self.assertEqual(report["sources"][0]["conversion_percent"], Decimal("25.00"))

    async def test_invalid_period_is_rejected_before_query(self):
        with self.assertRaises(ValueError):
            await get_analytics(FakeSession([]), date(2026, 11, 27), date(2026, 11, 1))

    def test_report_explains_ranking_basis_and_refunds(self):
        report = {
            "period": (date(2026, 11, 1), date(2026, 11, 27)), "leads": 4,
            "assignments": 2, "conversion_percent": Decimal("50.00"),
            "completed_paid_lessons": 3, "earnings": Decimal("450"),
            "net_payments": Decimal("200"), "payments": Decimal("250"),
            "refunds": Decimal("50"), "overdue_assignments": 1,
            "overdue_amount": Decimal("100"),
            "sources": [{"source": "A&B", "leads": 2, "converted_leads": 1,
                         "conversion_percent": Decimal("50.00")}],
            "tutors": [{"tutor": "Tutor", "completed_paid_lessons": 3,
                        "earnings": Decimal("450")}],
            "monthly": [],
        }
        output = format_analytics(report)
        self.assertIn("250.00 − возвраты 50.00", output)
        self.assertIn("без весового рейтинга", output)
        self.assertIn("A&B", output)


if __name__ == "__main__":
    unittest.main()
