import asyncio
import unittest
from decimal import Decimal

from bot.services.tutor_payments import create_tutor_payment_batch, parse_allocation_lines


class NoDatabaseSession:
    async def scalar(self, *_args, **_kwargs):
        raise AssertionError("validation should happen before database access")


class TutorPaymentInputTests(unittest.TestCase):
    def run_async(self, operation):
        return asyncio.run(operation)

    def test_parses_multiple_assignment_allocations_and_decimal_comma(self):
        self.assertEqual(
            parse_allocation_lines("12=1500\n13 = 250,50"),
            [(12, Decimal("1500")), (13, Decimal("250.50"))],
        )

    def test_rejects_duplicate_ids_and_invalid_amounts(self):
        for value in ("1=10\n1=2", "1=0", "-1=10", "1=NaN", "nope"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_allocation_lines(value)

    def test_rejects_allocation_sum_mismatch_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "совпадать"):
            self.run_async(create_tutor_payment_batch(
                NoDatabaseSession(), tutor_id=1, amount=Decimal("100"),
                allocations=[(1, Decimal("60")), (2, Decimal("30"))], operation_key="test-key",
            ))

    def test_rejects_non_decimal_payment_amount_before_database_access(self):
        for amount in (100, Decimal("0"), Decimal("NaN")):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.run_async(create_tutor_payment_batch(
                    NoDatabaseSession(), tutor_id=1, amount=amount,
                    allocations=[(1, Decimal("100"))], operation_key="test-key",
                ))


if __name__ == "__main__":
    unittest.main()
