import unittest
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from bot.services.debt_reminders import format_overdue_message, seconds_until_next_reminder


class DebtReminderTests(unittest.TestCase):
    def test_next_reminder_is_today_if_schedule_has_not_passed(self):
        now = datetime(2026, 11, 27, 9, 30, tzinfo=ZoneInfo("Europe/Moscow"))
        self.assertEqual(seconds_until_next_reminder(now, time(10, 0)), 1800)

    def test_next_reminder_moves_to_tomorrow_after_schedule(self):
        now = datetime(2026, 11, 27, 10, 0, 1, tzinfo=ZoneInfo("Europe/Moscow"))
        self.assertEqual(seconds_until_next_reminder(now, time(10, 0)), 86399)

    def test_reminder_lists_overdue_amount_and_days(self):
        due = datetime(2026, 11, 25).date()
        message = format_overdue_message([{
            "assignment_id": 12,
            "payment_due_date": due,
            "remaining_amount": 1500,
            "today": datetime(2026, 11, 27).date(),
        }])
        self.assertIn("Передача №12", message)
        self.assertIn("1500", message)
        self.assertIn("просрочка 2 дн.", message)


if __name__ == "__main__":
    unittest.main()
