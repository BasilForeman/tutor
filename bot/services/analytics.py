from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def local_today() -> date:
    try:
        zone = ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow"))
    except Exception as exc:
        raise ValueError("Некорректная TIMEZONE для аналитики") from exc
    return datetime.now(zone).date()


def period_bounds(period: str, today: date | None = None) -> tuple[date, date]:
    today = today or local_today()
    if period == "today":
        return today, today
    if period == "7d":
        return today - timedelta(days=6), today
    if period == "month":
        return today.replace(day=1), today
    if period == "previous_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    raise ValueError("Неизвестный период статистики")


async def get_analytics(session: AsyncSession, start_date: date, end_date: date) -> dict:
    """Aggregate event metrics for an inclusive period and current debt snapshot."""
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise ValueError("Укажите даты периода")
    if start_date > end_date:
        raise ValueError("Начало периода позже окончания")
    params = {"start": start_date, "end": end_date}

    summary = (await session.execute(text("""SELECT
        (SELECT COUNT(*) FROM leads WHERE created_at::date BETWEEN :start AND :end) AS leads,
        (SELECT COUNT(DISTINCT l.id) FROM leads l JOIN assignments a ON a.lead_id=l.id
          WHERE l.created_at::date BETWEEN :start AND :end AND a.assignment_date <= :end) AS converted_leads,
        (SELECT COUNT(*) FROM assignments WHERE assignment_date BETWEEN :start AND :end) AS assignments,
        (SELECT COUNT(*) FROM assignments WHERE NOT is_closed AND assignment_date <= :end) AS active_assignments,
        (SELECT COUNT(*) FROM assignments WHERE is_closed AND closed_at::date BETWEEN :start AND :end) AS closed_assignments,
        (SELECT COUNT(*) FROM lessons WHERE lesson_date BETWEEN :start AND :end AND status='completed') AS completed_lessons,
        (SELECT COUNT(*) FROM lessons WHERE lesson_date BETWEEN :start AND :end AND status='completed' AND lesson_type='trial') AS trial_lessons,
        (SELECT COUNT(*) FROM lessons WHERE lesson_date BETWEEN :start AND :end AND status='completed' AND lesson_type='paid') AS paid_lessons,
        (SELECT COUNT(*) FROM lessons WHERE lesson_date BETWEEN :start AND :end AND status='cancelled') AS cancelled_lessons,
        COALESCE((SELECT SUM(amount) FROM lessons WHERE lesson_date BETWEEN :start AND :end
          AND lesson_type='paid' AND status='completed'),0) AS earnings,
        COALESCE((SELECT SUM(amount) FROM payments WHERE payment_date BETWEEN :start AND :end),0) AS payments,
        COALESCE((SELECT SUM(amount) FROM payment_refunds WHERE refund_date BETWEEN :start AND :end),0) AS refunds,
        COALESCE((SELECT SUM(amount) FROM commission_accruals WHERE created_at::date BETWEEN :start AND :end),0)
          + COALESCE((SELECT SUM(difference) FROM assignment_adjustments WHERE created_at::date BETWEEN :start AND :end),0)
          AS commission_accrued,
        COALESCE((SELECT SUM(GREATEST(remaining_amount,0)) FROM assignment_finances),0) AS current_debt,
        (SELECT COUNT(*) FROM (SELECT a.tutor_id FROM assignments a JOIN assignment_finances f ON f.assignment_id=a.id
          GROUP BY a.tutor_id HAVING SUM(GREATEST(f.remaining_amount,0)) > 0) debtors) AS debtor_tutors,
        COALESCE((SELECT AVG(debt) FROM (SELECT a.tutor_id, SUM(GREATEST(f.remaining_amount,0)) AS debt
          FROM assignments a JOIN assignment_finances f ON f.assignment_id=a.id GROUP BY a.tutor_id
          HAVING SUM(GREATEST(f.remaining_amount,0)) > 0) d),0) AS average_tutor_debt,
        (SELECT COUNT(*) FROM payment_refunds WHERE refund_date BETWEEN :start AND :end) AS refund_count
    """), params)).mappings().one()

    sources = (await session.execute(text("""SELECT s.id AS source_id, s.name AS source,
        COUNT(DISTINCT l.id) AS leads,
        COUNT(DISTINCT a.id) AS assignments,
        COUNT(DISTINCT a.lead_id) AS converted_leads,
        CASE WHEN COUNT(DISTINCT l.id)=0 THEN 0::numeric
             ELSE ROUND(COUNT(DISTINCT a.lead_id)::numeric*100/COUNT(DISTINCT l.id),2) END AS conversion_percent
        FROM lead_sources s LEFT JOIN leads l ON l.source_id=s.id
          AND l.created_at::date BETWEEN :start AND :end
        LEFT JOIN assignments a ON a.lead_id=l.id AND a.assignment_date BETWEEN :start AND :end
        GROUP BY s.id, s.name ORDER BY leads DESC, s.id
    """), params)).mappings().all()

    tutors = (await session.execute(text("""SELECT t.id AS tutor_id, t.nickname AS tutor,
        (SELECT COUNT(*) FROM assignments a WHERE a.tutor_id=t.id AND a.assignment_date BETWEEN :start AND :end) AS assignments,
        (SELECT COUNT(*) FROM assignments a WHERE a.tutor_id=t.id AND NOT a.is_closed AND a.assignment_date <= :end) AS active_assignments,
        (SELECT COUNT(*) FROM assignments a WHERE a.tutor_id=t.id AND a.is_closed AND a.closed_at::date BETWEEN :start AND :end) AS closed_assignments,
        (SELECT COUNT(*) FROM lessons l JOIN assignments a ON a.id=l.assignment_id
          WHERE a.tutor_id=t.id AND l.lesson_date BETWEEN :start AND :end AND l.status='completed') AS completed_lessons,
        (SELECT COUNT(*) FROM lessons l JOIN assignments a ON a.id=l.assignment_id
          WHERE a.tutor_id=t.id AND l.lesson_date BETWEEN :start AND :end AND l.status='completed' AND l.lesson_type='trial') AS trial_lessons,
        (SELECT COUNT(*) FROM lessons l JOIN assignments a ON a.id=l.assignment_id
          WHERE a.tutor_id=t.id AND l.lesson_date BETWEEN :start AND :end AND l.status='completed' AND l.lesson_type='paid') AS paid_lessons,
        (SELECT COALESCE(SUM(l.amount),0) FROM lessons l JOIN assignments a ON a.id=l.assignment_id
          WHERE a.tutor_id=t.id AND l.lesson_date BETWEEN :start AND :end AND l.status='completed' AND l.lesson_type='paid') AS earnings,
        (SELECT COALESCE(SUM(c.amount),0) FROM commission_accruals c JOIN assignments a ON a.id=c.assignment_id
          WHERE a.tutor_id=t.id AND c.created_at::date BETWEEN :start AND :end)
          + (SELECT COALESCE(SUM(x.difference),0) FROM assignment_adjustments x JOIN assignments a ON a.id=x.assignment_id
          WHERE a.tutor_id=t.id AND x.created_at::date BETWEEN :start AND :end) AS commission_accrued,
        (SELECT COALESCE(SUM(p.amount),0)-COALESCE((SELECT SUM(r.amount) FROM payment_refunds r
          JOIN assignments ar ON ar.id=r.assignment_id WHERE ar.tutor_id=t.id AND r.refund_date BETWEEN :start AND :end),0)
          FROM payments p JOIN assignments a ON a.id=p.assignment_id
          WHERE a.tutor_id=t.id AND p.payment_date BETWEEN :start AND :end) AS net_payments,
        (SELECT COUNT(*) FROM payment_refunds r JOIN assignments a ON a.id=r.assignment_id
          WHERE a.tutor_id=t.id AND r.refund_date BETWEEN :start AND :end) AS refund_count,
        (SELECT COALESCE(SUM(GREATEST(f.remaining_amount,0)),0) FROM assignment_finances f
          JOIN assignments a ON a.id=f.assignment_id WHERE a.tutor_id=t.id) AS current_debt
        FROM tutors t WHERE t.is_active
        ORDER BY earnings DESC, completed_lessons DESC, t.id
    """), params)).mappings().all()

    debtors = (await session.execute(text("""SELECT t.id AS tutor_id, t.nickname AS tutor,
        SUM(GREATEST(f.remaining_amount, 0)) AS current_debt
        FROM tutors t JOIN assignments a ON a.tutor_id=t.id
        JOIN assignment_finances f ON f.assignment_id=a.id
        GROUP BY t.id,t.nickname
        HAVING SUM(GREATEST(f.remaining_amount, 0)) > 0
        ORDER BY current_debt DESC,t.id
    """), {})).mappings().all()

    daily = (await session.execute(text("""SELECT d.day::date AS day,
        (SELECT COUNT(*) FROM assignments a WHERE a.assignment_date=d.day::date) AS transfers,
        (SELECT COUNT(*) FROM lessons l WHERE l.lesson_date=d.day::date AND l.status='completed') AS lessons,
        (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.payment_date=d.day::date)
          - (SELECT COALESCE(SUM(r.amount),0) FROM payment_refunds r WHERE r.refund_date=d.day::date) AS net_payments,
        (SELECT COALESCE(SUM(c.amount),0) FROM commission_accruals c WHERE c.created_at::date=d.day::date)
          + (SELECT COALESCE(SUM(x.difference),0) FROM assignment_adjustments x WHERE x.created_at::date=d.day::date) AS commission_accrued
        FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d(day)
        ORDER BY day
    """), params)).mappings().all()

    result = dict(summary)
    result["net_payments"] = (result["payments"] or Decimal("0")) - (result["refunds"] or Decimal("0"))
    result["conversion_percent"] = (
        Decimal(result["converted_leads"] or 0) * 100 / Decimal(result["leads"])
        if result["leads"] else Decimal("0")
    ).quantize(Decimal("0.01"))
    result["sources"] = [dict(row) for row in sources]
    result["tutors"] = [dict(row) for row in tutors]
    result["debtors"] = [dict(row) for row in debtors]
    result["daily"] = [dict(row) for row in daily]
    result["period"] = (start_date, end_date)
    return result


def _money(value) -> str:
    return str((value or Decimal("0")).quantize(Decimal("0.01")))


def _bar(value, maximum, width=10) -> str:
    if not maximum or not value:
        return "·"
    return "█" * max(1, min(width, round(float(value) / float(maximum) * width)))


def format_analytics(report: dict, *, limit: int = 8) -> str:
    """Compact text report; event metrics use the selected period, debt is current."""
    start, end = report["period"]
    lines = [
        f"📊 Статистика: {start:%d.%m.%Y}–{end:%d.%m.%Y}",
        f"Передачи: {report['assignments']} | заявки: {report['leads']} | уникальных передано: {report['converted_leads']} | конверсия: {report['conversion_percent']}%",
        f"Активно сейчас: {report.get('active_assignments', 0)} | закрыто за период: {report.get('closed_assignments', 0)} | денежных возвратов: {report.get('refund_count', 0)}",
        f"Занятия: проведено {report.get('completed_lessons', report.get('completed_paid_lessons', 0))} | пробных {report.get('trial_lessons', 0)} | платных {report.get('paid_lessons', report.get('completed_paid_lessons', 0))} | отменено {report.get('cancelled_lessons', 0)}",
        f"Заработок по платным занятиям: {_money(report['earnings'])}",
        f"Комиссия начислена за период: {_money(report.get('commission_accrued', 0))}",
        f"Платежи получены: {_money(report['payments'])} | возвраты денег: {_money(report['refunds'])} | нетто: {_money(report['net_payments'])}",
        f"Текущий долг: {_money(report.get('current_debt', report.get('overdue_amount', 0)))} | репетиторов с долгом: {report.get('debtor_tutors', report.get('overdue_assignments', 0))} | средний долг: {_money(report.get('average_tutor_debt', 0))}",
    ]
    if report.get("sources"):
        lines.append("\nПо источникам (заявки / передачи / конверсия заявок):")
        source_total = sum((row["leads"] for row in report["sources"]), 0)
        lines.extend(
            f"• {row['source']}: {row['leads']} / {row.get('assignments', row.get('converted_leads', 0))} / "
            f"{row['conversion_percent']}% конверсия / "
            f"{(Decimal(row['leads']) * 100 / Decimal(source_total)).quantize(Decimal('0.1')) if source_total else Decimal('0')}% доля"
            for row in report["sources"][:limit]
        )
    if report.get("tutors"):
        lines.append("\nРепетиторы (передачи / занятия / начислено / получено / текущий долг):")
        lines.extend(
            f"• {row['tutor']}: {row.get('assignments', 0)} / {row.get('completed_lessons', row.get('completed_paid_lessons', 0))} / "
            f"{_money(row.get('commission_accrued', 0))} / {_money(row.get('net_payments', 0))} / {_money(row.get('current_debt', 0))}"
            for row in report["tutors"][:limit]
        )
    days = report.get("daily", [])
    if days:
        recent = days[-14:]
        max_transfer = max((row["transfers"] for row in recent), default=0)
        max_lessons = max((row["lessons"] for row in recent), default=0)
        max_payments = max((row["net_payments"] for row in recent), default=Decimal("0"))
        max_commission = max((row["commission_accrued"] for row in recent), default=Decimal("0"))
        lines.append("\nДинамика (последние 14 дней периода): дата | передачи | занятия | выплаты нетто | начислено")
        lines.extend(
            f"{row['day']:%d.%m}: {_bar(row['transfers'], max_transfer)} {row['transfers']} | "
            f"{_bar(row['lessons'], max_lessons)} {row['lessons']} | "
            f"{_bar(row['net_payments'], max_payments)} {_money(row['net_payments'])} | "
            f"{_bar(row['commission_accrued'], max_commission)} {_money(row['commission_accrued'])}"
            for row in recent
        )
    if report.get("debtors"):
        lines.append("\nКрупнейшие текущие долги:")
        lines.extend(f"• {row['tutor']}: {_money(row['current_debt'])} ₽" for row in report["debtors"][:limit])
    return "\n".join(lines)
