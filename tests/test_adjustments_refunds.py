import asyncio
import unittest
from decimal import Decimal

from bot.services.finance import adjust_assignment_commission
from bot.services.payments import refund_payment


class NoDatabaseSession:
    async def scalar(self, statement):
        raise AssertionError("validation must happen before database access")


class AdjustmentAndRefundValidationTests(unittest.TestCase):
    def run_async(self, operation):
        return asyncio.run(operation)

    def test_adjustment_rejects_negative_or_non_finite_amount(self):
        for amount in (Decimal("-1"), Decimal("NaN"), 1.0):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.run_async(adjust_assignment_commission(
                    NoDatabaseSession(), 1, amount, "reason", "author", "adjustment-key"
                ))

    def test_adjustment_requires_a_reason_and_author(self):
        with self.assertRaisesRegex(ValueError, "причину"):
            self.run_async(adjust_assignment_commission(
                NoDatabaseSession(), 1, Decimal("100"), "", "author", "adjustment-key"
            ))

    def test_refund_rejects_zero_negative_or_non_finite_amount(self):
        for amount in (Decimal("0"), Decimal("-1"), Decimal("Infinity"), 5.0):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.run_async(refund_payment(
                    NoDatabaseSession(), 1, 2, amount, "reason", "author", "refund-key"
                ))

    def test_refund_requires_reason_and_author(self):
        with self.assertRaisesRegex(ValueError, "причину"):
            self.run_async(refund_payment(
                NoDatabaseSession(), 1, 2, Decimal("10"), "", "author", "refund-key"
            ))


if __name__ == "__main__":
    unittest.main()
