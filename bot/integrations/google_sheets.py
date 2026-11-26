import os
from collections.abc import Mapping

import asyncio

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import text

from bot.database.connection import async_session


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]


HEADERS = {
    "Assignments": [
        "ID",
        "Дата передачи",
        "Репетитор",
        "Ученик",
        "Источник",
        "Кто передал",
        "Ставка",
        "Комиссия",
        "Дата оплаты",
        "Примечание",
    ],
    "Payments": [
        "ID платежа",
        "ID назначения",
        "Репетитор",
        "Ученик",
        "Дата платежа",
        "Сумма",
        "Примечание",
    ],
    "Finances": [
        "ID назначения",
        "Репетитор",
        "Ученик",
        "Комиссия",
        "Оплачено",
        "Остаток",
    ],
    "Dashboard": [
        "Показатель",
        "Значение",
    ],
}


async def get_database_data():
    async with async_session() as session:

        assignments_query = text("""
            SELECT
                a.id,
                a.assignment_date,
                t.nickname AS tutor,
                c.nickname AS client,
                ls.name AS source,
                a.assigned_by,
                a.rate,
                a.commission_amount,
                a.payment_due_date,
                a.notes
            FROM assignments a
            JOIN tutors t ON t.id = a.tutor_id
            JOIN clients c ON c.id = a.client_id
            JOIN lead_sources ls ON ls.id = a.source_id
            ORDER BY a.id
        """)

        payments_query = text("""
            SELECT
                p.id,
                p.assignment_id,
                t.nickname AS tutor,
                c.nickname AS client,
                p.payment_date,
                p.amount,
                p.notes
            FROM payments p
            JOIN assignments a ON a.id = p.assignment_id
            JOIN tutors t ON t.id = a.tutor_id
            JOIN clients c ON c.id = a.client_id
            ORDER BY p.id
        """)

        finances_query = text("""
            SELECT
                af.assignment_id,
                t.nickname AS tutor,
                c.nickname AS client,
                af.commission_amount,
                af.paid_amount,
                af.remaining_amount
            FROM assignment_finances af
            JOIN assignments a ON a.id = af.assignment_id
            JOIN tutors t ON t.id = a.tutor_id
            JOIN clients c ON c.id = a.client_id
            ORDER BY af.assignment_id
        """)

        assignments = (
            await session.execute(assignments_query)
        ).mappings().all()

        payments = (
            await session.execute(payments_query)
        ).mappings().all()

        finances = (
            await session.execute(finances_query)
        ).mappings().all()

        dashboard_query = text("""
            SELECT
                COUNT(*) AS assignments_count,
                COALESCE(SUM(commission_amount), 0) AS total_commission,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(remaining_amount), 0) AS total_debt
            FROM assignment_finances
        """)

        dashboard = (
            await session.execute(dashboard_query)
        ).mappings().one()

        payments_total_query = text("""
            SELECT COALESCE(SUM(amount), 0)
            FROM payments
        """)

        payments_total = (
            await session.execute(payments_total_query)
        ).scalar_one()

    dashboard_rows = [
        ["Количество назначений", dashboard["assignments_count"]],
        ["Общая комиссия", dashboard["total_commission"]],
        ["Получено платежей", payments_total],
        ["Текущая задолженность", dashboard["total_debt"]],
    ]

    return {
        "Assignments": assignments,
        "Payments": payments,
        "Finances": finances,
        "Dashboard": dashboard_rows,
    }


def get_spreadsheet():
    credentials_path = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        "credentials/google_credentials.json"
    )

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")

    if not spreadsheet_id:
        raise ValueError("GOOGLE_SHEETS_ID не указан в .env")

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Не найден JSON-ключ: {credentials_path}"
        )

    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    client = gspread.authorize(credentials)

    return client.open_by_key(spreadsheet_id)



def update_sheet(spreadsheet, sheet_name, rows):
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=1000,
            cols=20
        )

    headers = HEADERS[sheet_name]
    values = [headers]

    for row in rows:
        if isinstance(row, Mapping):
            values.append([
                str(value) if value is not None else ""
                for value in row.values()
            ])
        else:
            values.append([
                str(value) if value is not None else ""
                for value in row
            ])

    worksheet.update(
        range_name="A1",
        values=values,
        value_input_option="RAW"
    )

    print(f"Лист {sheet_name}: записано {len(rows)} строк")

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=1000,
            cols=20
        )

    headers = HEADERS[sheet_name]

    values = [headers]

    for row in rows:
        if isinstance(row, Mapping):
            values.append([
                str(value) if value is not None else ""
                for value in row.values()
            ])
        else:
            values.append([
                str(value) if value is not None else ""
                for value in row
            ])

    worksheet.update(
        range_name="A1",
        values=values,
        value_input_option="RAW"
    )

    print(f"Лист {sheet_name}: записано {len(rows)} строк")
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=1000,
            cols=20
        )

    headers = HEADERS[sheet_name]

    values = [headers]

    for row in rows:
        if isinstance(row, Mapping):
            values.append([
                str(value) if value is not None else ""
                for value in row.values()
            ])
        else:
            values.append([
                str(value) if value is not None else ""
                for value in row
            ])

    worksheet.clear()

    worksheet.update(
        values=values,
        range_name="A1"
    )


def sync_to_google_sheets(data):
    spreadsheet = get_spreadsheet()

    for sheet_name, rows in data.items():
        update_sheet(
            spreadsheet,
            sheet_name,
            rows
        )

    print("Google Sheets: синхронизация завершена!")


async def sync_all():
    data = await get_database_data()

    await asyncio.to_thread(
        sync_to_google_sheets,
        data
    )

    return True
