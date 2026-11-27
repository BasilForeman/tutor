from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_analytics(session: AsyncSession, start_date: date, end_date: date) -> dict:
    """Read-only period report. Date bounds are inclusive and based on event dates."""
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise ValueError("Укажите даты периода")
    if start_date > end_date:
        raise ValueError("Начало периода позже окончания")

    summary = (await session.execute(text("""SELECT
        (SELECT COUNT(*) FROM leads WHERE created_at::date BETWEEN :start AND :end) AS leads,
        (SELECT COUNT(DISTINCT l.id) FROM leads l JOIN assignments a ON a.lead_id=l.id
          WHERE l.created_at::date BETWEEN :start AND :end) AS converted_leads,
        (SELECT COUNT(*) FROM assignments WHERE assignment_date BETWEEN :start AND :end) AS assignments,
        (SELECT COUNT(*) FROM lessons WHERE lesson_date BETWEEN :start AND :end
          AND lesson_type='paid' AND status='completed') AS completed_paid_lessons,
        COALESCE((SELECT SUM(amount) FROM lessons WHERE lesson_date BETWEEN :start AND :end
          AND lesson_type='paid' AND status='completed'),0) AS earnings,
        COALESCE((SELECT SUM(amount) FROM payments WHERE payment_date BETWEEN :start AND :end),0) AS payments,
        COALESCE((SELECT SUM(amount) FROM payment_refunds WHERE refund_date BETWEEN :start AND :end),0) AS refunds,
        (SELECT COUNT(*) FROM assignments a JOIN assignment_finances f ON f.assignment_id=a.id
          WHERE f.remaining_amount > 0 AND a.payment_due_date < CURRENT_DATE) AS overdue_assignments,
        COALESCE((SELECT SUM(f.remaining_amount) FROM assignments a
          JOIN assignment_finances f ON f.assignment_id=a.id
          WHERE f.remaining_amount > 0 AND a.payment_due_date < CURRENT_DATE),0) AS overdue_amount
    """), {"start": start_date, "end": end_date})).mappings().one()

    sources = (await session.execute(text("""SELECT s.id AS source_id, s.name AS source,
        COUNT(DISTINCT l.id) AS leads, COUNT(DISTINCT a.lead_id) AS converted_leads,
        CASE WHEN COUNT(DISTINCT l.id)=0 THEN 0::numeric
             ELSE ROUND(COUNT(DISTINCT a.lead_id)::numeric*100/COUNT(DISTINCT l.id),2) END AS conversion_percent
        FROM lead_sources s LEFT JOIN leads l ON l.source_id=s.id
          AND l.created_at::date BETWEEN :start AND :end
        LEFT JOIN assignments a ON a.lead_id=l.id
        GROUP BY s.id, s.name ORDER BY leads DESC, s.id
    """), {"start": start_date, "end": end_date})).mappings().all()

    monthly = (await session.execute(text("""SELECT to_char(month_start, 'YYYY-MM') AS month,
        COUNT(*) AS paid_lessons, COALESCE(SUM(amount),0) AS earnings FROM (
          SELECT date_trunc('month', lesson_date)::date AS month_start, amount
          FROM lessons WHERE lesson_date BETWEEN :start AND :end
            AND lesson_type='paid' AND status='completed'
        ) x GROUP BY month_start ORDER BY month_start
    """), {"start": start_date, "end": end_date})).mappings().all()

    tutors = (await session.execute(text("""SELECT t.id AS tutor_id, t.nickname AS tutor,
        COUNT(l.id) AS completed_paid_lessons, COALESCE(SUM(l.amount),0) AS earnings
        FROM tutors t LEFT JOIN assignments a ON a.tutor_id=t.id
        LEFT JOIN lessons l ON l.assignment_id=a.id AND l.lesson_date BETWEEN :start AND :end
          AND l.lesson_type='paid' AND l.status='completed'
        GROUP BY t.id, t.nickname ORDER BY earnings DESC, completed_paid_lessons DESC, t.id
    """), {"start": start_date, "end": end_date})).mappings().all()

    result = dict(summary)
    result["net_payments"] = (result["payments"] or Decimal("0")) - (result["refunds"] or Decimal("0"))
    result["conversion_percent"] = (
        Decimal(result["converted_leads"] or 0) * 100 / Decimal(result["leads"])
        if result["leads"] else Decimal("0")
    ).quantize(Decimal("0.01"))
    result["sources"] = [dict(row) for row in sources]
    result["monthly"] = [dict(row) for row in monthly]
    result["tutors"] = [dict(row) for row in tutors]
    result["period"] = (start_date, end_date)
    return result


def format_analytics(report: dict, *, limit: int = 8) -> str:
    """Plain-text Telegram-safe summary; ranking is by raw earnings only."""
    start, end = report["period"]
    def money(value):
        return str((value or Decimal("0")).quantize(Decimal("0.01")))

    lines = [
        f"Аналитика за {start:%d.%m.%Y}–{end:%d.%m.%Y}",
        f"Заявки: {report['leads']} | передачи: {report['assignments']} | конверсия заявок: {report['conversion_percent']}%",
        f"Платные занятия: {report['completed_paid_lessons']} | заработок: {money(report['earnings'])}",
        f"Получено: {money(report['net_payments'])} (платежи {money(report['payments'])} − возвраты {money(report['refunds'])})",
        f"Просроченные комиссии: {report['overdue_assignments']} передач на {money(report['overdue_amount'])}",
        "\nПо источникам (заявки / назначенные уникальные заявки / конверсия):",
    ]
    lines.extend(f"• {row['source']}: {row['leads']} / {row['converted_leads']} / {row['conversion_percent']}%" for row in report["sources"][:limit])
    lines.append("\nРепетиторы по заработку от платных проведённых занятий (без весового рейтинга):")
    lines.extend(f"• {row['tutor']}: {row['completed_paid_lessons']} занятий, {money(row['earnings'])}" for row in report["tutors"][:limit])
    if report["monthly"]:
        lines.append("\nДинамика по месяцам:")
        lines.extend(f"• {row['month']}: {row['paid_lessons']} занятий, {money(row['earnings'])}" for row in report["monthly"])
    return "\n".join(lines)
