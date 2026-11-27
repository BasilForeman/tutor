"""One-way, repeatable PostgreSQL snapshot export to dedicated Sheets tabs."""
from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import text

from bot.database.connection import async_session

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# These tabs and columns are owned by this integration. Other columns and tabs
# are left untouched. IDs are always included so consumers can identify rows.
HEADERS = {
    "Tutors": ["ID", "Имя", "Предмет", "Активен", "Создан"],
    "Clients": ["ID", "Имя", "Контакт", "Примечание", "Активен", "Создан"],
    "LeadSources": ["ID", "Источник", "Активен"],
    "Leads": ["ID", "Ученик ID", "Ученик", "Источник ID", "Источник", "Предмет", "Статус", "Причина отказа", "Создан"],
    "Assignments": ["ID", "Lead ID", "Дата", "Репетитор ID", "Репетитор", "Ученик ID", "Ученик", "Источник", "Кто передал", "Ставка", "Режим комиссии", "Комиссия", "Ставка комиссии %", "Срок оплаты", "Закрыта", "Причина закрытия", "Примечание"],
    "Lessons": ["ID", "Assignment ID", "Дата", "Тип", "Статус", "Заработок", "Примечание"],
    "Payments": ["ID", "Assignment ID", "Дата", "Сумма", "Возвраты", "Нетто", "Примечание"],
    "Finances": ["Assignment ID", "Репетитор", "Ученик", "Комиссия", "Оплачено нетто", "Остаток", "Согласовано"],
    "Adjustments": ["ID", "Assignment ID", "Комиссия до", "Комиссия после", "Разница", "Причина", "Автор", "Создан"],
    "Dashboard": ["Показатель", "Значение", "Период / определение", "Сформировано"],
}


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return str(value)


async def get_database_data():
    """Read a consistent set of DB-backed rows for the owned tabs."""
    queries = {
        "Tutors": "SELECT id, nickname, subject, is_active, created_at FROM tutors ORDER BY id",
        "Clients": "SELECT id, nickname, contact, notes, is_active, created_at FROM clients ORDER BY id",
        "LeadSources": "SELECT id, name, is_active FROM lead_sources ORDER BY id",
        "Leads": """SELECT l.id, l.client_id, c.nickname AS client, l.source_id, s.name AS source,
                    l.subject, l.status, l.lost_reason, l.created_at
                    FROM leads l JOIN clients c ON c.id=l.client_id
                    JOIN lead_sources s ON s.id=l.source_id ORDER BY l.id""",
        "Assignments": """SELECT a.id, a.lead_id, a.assignment_date, a.tutor_id, t.nickname AS tutor,
                    a.client_id, c.nickname AS client, s.name AS source, a.assigned_by, a.rate,
                    a.commission_mode, a.commission_amount, a.commission_percentage,
                    a.payment_due_date, a.is_closed, a.close_reason, a.notes
                    FROM assignments a JOIN tutors t ON t.id=a.tutor_id
                    JOIN clients c ON c.id=a.client_id JOIN lead_sources s ON s.id=a.source_id
                    ORDER BY a.id""",
        "Lessons": "SELECT id, assignment_id, lesson_date, lesson_type, status, amount, notes FROM lessons ORDER BY id",
        "Payments": """SELECT p.id, p.assignment_id, p.payment_date, p.amount,
                    COALESCE(r.refunded, 0) AS refunded, p.amount-COALESCE(r.refunded, 0) AS net,
                    p.notes FROM payments p LEFT JOIN
                    (SELECT payment_id, SUM(amount) AS refunded FROM payment_refunds GROUP BY payment_id) r
                    ON r.payment_id=p.id ORDER BY p.id""",
        "Finances": """SELECT af.assignment_id, t.nickname AS tutor, c.nickname AS client,
                    af.commission_amount, af.paid_amount, af.remaining_amount, af.agreed_commission
                    FROM assignment_finances af JOIN assignments a ON a.id=af.assignment_id
                    JOIN tutors t ON t.id=a.tutor_id JOIN clients c ON c.id=a.client_id
                    ORDER BY af.assignment_id""",
        "Adjustments": """SELECT id, assignment_id, previous_amount, new_amount, difference,
                    reason, author, created_at FROM assignment_adjustments ORDER BY id""",
    }
    async with async_session() as session:
        data = {}
        # One transaction ensures all tabs reflect a single database snapshot.
        async with session.begin():
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            for name, sql in queries.items():
                result = await session.execute(text(sql))
                data[name] = [dict(row) for row in result.mappings().all()]
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            dashboard = await session.execute(text("""SELECT
                (SELECT COUNT(*) FROM leads) AS leads,
                (SELECT COUNT(DISTINCT lead_id) FROM assignments) AS converted_leads,
                (SELECT COUNT(*) FROM assignments) AS assignments,
                (SELECT COUNT(*) FROM lessons WHERE status='completed' AND lesson_type='paid') AS paid_lessons,
                COALESCE((SELECT SUM(amount) FROM lessons WHERE status='completed' AND lesson_type='paid'),0) AS tutor_earnings,
                COALESCE((SELECT SUM(amount) FROM payment_refunds),0) AS refunds,
                COALESCE((SELECT SUM(amount) FROM payments),0)-COALESCE((SELECT SUM(amount) FROM payment_refunds),0) AS net_payments,
                COALESCE((SELECT SUM(commission_amount) FROM assignment_finances),0) AS commission,
                COALESCE((SELECT SUM(GREATEST(remaining_amount,0)) FROM assignment_finances),0) AS debt,
                (SELECT COUNT(*) FROM assignments a JOIN assignment_finances f ON f.assignment_id=a.id
                    WHERE f.remaining_amount>0 AND a.payment_due_date<CURRENT_DATE) AS overdue_count,
                COALESCE((SELECT SUM(f.remaining_amount) FROM assignments a JOIN assignment_finances f ON f.assignment_id=a.id
                    WHERE f.remaining_amount>0 AND a.payment_due_date<CURRENT_DATE),0) AS overdue_amount"""))
            totals = dashboard.mappings().one()
            avg_commission = (totals["commission"] / totals["converted_leads"]
                              if totals["converted_leads"] else Decimal("0"))
            data["Dashboard"] = [[label, value, definition, now] for label, value, definition in (
                ("Заявки", totals["leads"], "Все заявки в базе"),
                ("Успешные заявки", totals["converted_leads"], "Уникальные Lead, имеющие хотя бы одну передачу"),
                ("Конверсия заявок, %", round(totals["converted_leads"] * 100 / totals["leads"], 2) if totals["leads"] else 0, "Успешные уникальные заявки / все заявки"),
                ("Передачи", totals["assignments"], "Все факты передачи, включая повторные"),
                ("Проведённые платные занятия", totals["paid_lessons"], "Все completed paid lessons"),
                ("Заработок репетиторов", totals["tutor_earnings"], "Сумма платных проведённых занятий"),
                ("Платежи нетто", totals["net_payments"], "Все платежи минус все возвраты"),
                ("Возвраты", totals["refunds"], "Все зарегистрированные возвраты"),
                ("Начисленная комиссия", totals["commission"], "Текущее значение assignment_finances"),
                ("Средняя начисленная комиссия на успешную заявку", avg_commission, "Начисленная комиссия / уникальные заявки с передачей"),
                ("Текущая задолженность", totals["debt"], "Сумма положительных остатков комиссий"),
                ("Просрочка", totals["overdue_count"], "Передачи с долгом и прошедшей датой оплаты"),
                ("Просроченная сумма", totals["overdue_amount"], "Сумма задолженности с прошедшей датой оплаты"),
            )]
    return data


def get_spreadsheet():
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/google_credentials.json")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        raise ValueError("GOOGLE_SHEETS_ID не указан")
    if not os.path.exists(credentials_path):
        raise FileNotFoundError("Файл сервисного аккаунта Google не найден")
    credentials = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(credentials).open_by_key(spreadsheet_id)


def _column_name(n: int) -> str:
    result = ""
    while n:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def update_sheet(spreadsheet, sheet_name, rows):
    if sheet_name not in HEADERS:
        raise ValueError(f"Неизвестный лист: {sheet_name}")
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(HEADERS[sheet_name]))

    values = [HEADERS[sheet_name]]
    for row in rows:
        if isinstance(row, Mapping):
            values.append([_cell(row.get(header_key)) for header_key in row.keys()])
        else:
            values.append([_cell(value) for value in row])
    # Current rows are deterministic snapshots, so replaying is an upsert by
    # stable ID in practice. Restrict writes/clears to our exact owned columns.
    end_col = _column_name(len(HEADERS[sheet_name]))
    old_rows = max(getattr(worksheet, "row_count", len(values)), len(values))
    worksheet.update(range_name=f"A1:{end_col}{len(values)}", values=values, value_input_option="RAW")
    if old_rows > len(values):
        worksheet.batch_clear([f"A{len(values)+1}:{end_col}{old_rows}"])
    return len(rows)


def sync_to_google_sheets(data, *, spreadsheet=None):
    spreadsheet = spreadsheet or get_spreadsheet()
    counts = {}
    for sheet_name in HEADERS:
        counts[sheet_name] = update_sheet(spreadsheet, sheet_name, data.get(sheet_name, []))
    return counts


def sync_one_sheet_to_google_sheets(sheet_name, rows):
    return update_sheet(get_spreadsheet(), sheet_name, rows)


async def _record_sync_result(success: bool, error: str | None = None, row_counts=None):
    # Migration 0012 creates this diagnostic-only table. Never store credentials,
    # request payloads, or user data in error messages.
    async with async_session() as session:
        await session.execute(text("""INSERT INTO google_sheets_sync_log
            (succeeded, error_type, row_counts, finished_at)
            VALUES (:succeeded, :error_type, CAST(:row_counts AS jsonb), CURRENT_TIMESTAMP)"""), {
                "succeeded": success, "error_type": error,
                "row_counts": __import__("json").dumps(row_counts or {}),
            })
        await session.commit()


async def sync_all(*, attempts: int = 4):
    if attempts < 1:
        raise ValueError("attempts должен быть положительным")
    data = await get_database_data()
    last_error = None
    for attempt in range(attempts):
        try:
            counts = await asyncio.to_thread(sync_to_google_sheets, data)
            await _record_sync_result(True, row_counts=counts)
            return True
        except Exception as exc:
            last_error = exc
            logger.warning("Google Sheets sync attempt %d/%d failed (%s)", attempt + 1, attempts, type(exc).__name__)
            if attempt + 1 < attempts:
                await asyncio.sleep(min(60, 2 ** attempt + random.random()))
    try:
        await _record_sync_result(False, error=type(last_error).__name__ if last_error else "UnknownError")
    except Exception:
        logger.exception("Could not persist Google Sheets sync failure")
    raise RuntimeError("Не удалось синхронизировать Google Sheets после повторных попыток") from last_error


async def sync_tutors():
    data = await get_database_data()
    await asyncio.to_thread(sync_one_sheet_to_google_sheets, "Tutors", data["Tutors"])
    return True


async def sync_loop(interval_seconds: int = 300):
    """Periodic full snapshots provide automatic retry/recovery after outages."""
    if interval_seconds < 30:
        raise ValueError("Интервал синхронизации не может быть меньше 30 секунд")
    while True:
        try:
            await sync_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Google Sheets sync cycle failed")
        await asyncio.sleep(interval_seconds)
