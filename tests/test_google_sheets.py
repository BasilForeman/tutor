import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from bot.integrations.google_sheets import HEADERS, _cell, _column_name, sync_all, sync_to_google_sheets, update_sheet


class FakeWorksheet:
    def __init__(self, row_count=20):
        self.row_count = row_count
        self.updates = []
        self.clears = []

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def batch_clear(self, ranges):
        self.clears.extend(ranges)


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, name):
        if name not in self.sheets:
            raise __import__("gspread").WorksheetNotFound(name)
        return self.sheets[name]

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = FakeWorksheet()
        return self.sheets[title]


class GoogleSheetsTests(unittest.TestCase):
    def test_all_specification_tabs_have_explicit_headers_and_stable_ids(self):
        self.assertEqual(set(HEADERS), {
            "Tutors", "Clients", "LeadSources", "Leads", "Assignments",
            "Lessons", "Payments", "Finances", "Adjustments", "Dashboard",
        })
        for tab in ("Tutors", "Clients", "LeadSources", "Leads", "Assignments", "Lessons", "Payments", "Finances", "Adjustments"):
            self.assertIn("ID", HEADERS[tab][0])

    def test_snapshot_only_clears_columns_owned_by_that_tab(self):
        sheet = FakeSpreadsheet()
        worksheet = FakeWorksheet(row_count=50)
        sheet.sheets["Tutors"] = worksheet
        update_sheet(sheet, "Tutors", [{"id": 7, "nickname": "Tutor", "subject": "Math", "is_active": True, "created_at": None}])
        self.assertEqual(worksheet.updates[0]["range_name"], "A1:E2")
        self.assertEqual(worksheet.clears, ["A3:E50"])
        self.assertEqual(worksheet.updates[0]["values"][1], ["7", "Tutor", "Math", "Да", ""])

    def test_snapshot_is_repeatable_and_uses_raw_values(self):
        sheet = FakeSpreadsheet()
        row = {"id": 2, "amount": Decimal("10.25")}
        update_sheet(sheet, "Tutors", [])
        tab = sheet.sheets["Tutors"]
        tab.row_count = 1
        update_sheet(sheet, "Tutors", [])
        self.assertEqual(tab.updates[0]["values"], tab.updates[1]["values"])
        self.assertEqual(tab.updates[0]["value_input_option"], "RAW")
        self.assertEqual(_cell(row["amount"]), "10.25")

    def test_column_name_supports_tabs_wider_than_z(self):
        self.assertEqual(_column_name(1), "A")
        self.assertEqual(_column_name(26), "Z")
        self.assertEqual(_column_name(27), "AA")

    def test_full_sync_creates_every_required_tab(self):
        spreadsheet = FakeSpreadsheet()
        counts = sync_to_google_sheets({}, spreadsheet=spreadsheet)
        self.assertEqual(set(spreadsheet.sheets), set(HEADERS))
        self.assertEqual(set(counts), set(HEADERS))

    def test_dashboard_definition_and_timestamp_columns_are_written(self):
        spreadsheet = FakeSpreadsheet()
        worksheet = FakeWorksheet(row_count=1)
        spreadsheet.sheets["Dashboard"] = worksheet
        update_sheet(spreadsheet, "Dashboard", [["Заявки", 2, "Все заявки", "2026-11-27T10:00:00+03:00"]])
        self.assertEqual(worksheet.updates[0]["range_name"], "A1:D2")
        self.assertEqual(worksheet.updates[0]["values"][0], HEADERS["Dashboard"])


class GoogleSheetsRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_error_retries_and_records_success(self):
        sync = Mock(side_effect=[TimeoutError(), TimeoutError(), {"Tutors": 1}])
        record = AsyncMock()
        async def no_wait(_):
            return None
        with patch("bot.integrations.google_sheets.get_database_data", new=AsyncMock(return_value={"Tutors": []})), \
             patch("bot.integrations.google_sheets.sync_to_google_sheets", new=sync), \
             patch("bot.integrations.google_sheets._record_sync_result", new=record), \
             patch("bot.integrations.google_sheets.asyncio.sleep", new=no_wait):
            self.assertTrue(await sync_all(attempts=3))
        self.assertEqual(sync.call_count, 3)
        record.assert_awaited_once_with(True, row_counts={"Tutors": 1})

    async def test_exhausted_retries_log_error_type_without_suppressing_failure(self):
        sync = Mock(side_effect=TimeoutError())
        record = AsyncMock()
        async def no_wait(_):
            return None
        with patch("bot.integrations.google_sheets.get_database_data", new=AsyncMock(return_value={})), \
             patch("bot.integrations.google_sheets.sync_to_google_sheets", new=sync), \
             patch("bot.integrations.google_sheets._record_sync_result", new=record), \
             patch("bot.integrations.google_sheets.asyncio.sleep", new=no_wait):
            with self.assertRaisesRegex(RuntimeError, "повторных попыток"):
                await sync_all(attempts=2)
        self.assertEqual(sync.call_count, 2)
        record.assert_awaited_once_with(False, error="TimeoutError")


if __name__ == "__main__":
    unittest.main()
