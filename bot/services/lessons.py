from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Assignment, CommissionAccrual, Lesson


async def create_lesson(
    session: AsyncSession,
    assignment_id: int,
    lesson_type: str,
    status: str,
    lesson_date: date,
    operation_key: str,
    amount: Optional[Decimal] = None,
    notes: Optional[str] = None,
) -> Lesson:
    if lesson_type not in {"trial", "paid"}:
        raise ValueError("Тип занятия должен быть trial или paid")
    if status not in {"completed", "cancelled"}:
        raise ValueError("Статус занятия должен быть completed или cancelled")
    if amount is not None and (
        not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0
    ):
        raise ValueError("Стоимость занятия должна быть конечным неотрицательным Decimal")
    if lesson_type == "paid" and status == "completed" and (amount is None or amount <= 0):
        raise ValueError("Для проведённого платного занятия укажите стоимость")
    if lesson_type == "trial" and amount not in (None, Decimal("0")):
        raise ValueError("Пробное занятие не может иметь стоимость")
    if status == "cancelled":
        amount = None
    if notes is not None and not isinstance(notes, str):
        raise ValueError("Комментарий должен быть текстом")
    notes = notes.strip() if notes else None
    operation_key = (operation_key or "").strip()
    if not operation_key or len(operation_key) > 128:
        raise ValueError("Не задан корректный ключ операции занятия")

    existing = await session.scalar(
        select(Lesson).where(Lesson.operation_key == operation_key)
    )
    if existing:
        same_payload = (
            existing.assignment_id == assignment_id
            and existing.lesson_type == lesson_type
            and existing.status == status
            and existing.lesson_date == lesson_date
            and existing.amount == amount
            and (notes is None or existing.notes == notes)
        )
        if not same_payload:
            raise ValueError("Ключ операции уже использован для другого занятия")
        return existing

    try:
        assignment = await session.scalar(
            select(Assignment).where(Assignment.id == assignment_id).with_for_update()
        )
        if not assignment:
            raise ValueError("Передача не найдена")
        if assignment.is_closed:
            raise ValueError("Нельзя добавить занятие в закрытую передачу")
        # Serialize concurrent retries on the assignment row, then recheck the key.
        existing = await session.scalar(
            select(Lesson).where(Lesson.operation_key == operation_key)
        )
        if existing:
            same_payload = (
                existing.assignment_id == assignment_id
                and existing.lesson_type == lesson_type
                and existing.status == status
                and existing.lesson_date == lesson_date
                and existing.amount == amount
                and (notes is None or existing.notes == notes)
            )
            if not same_payload:
                raise ValueError("Ключ операции уже использован для другого занятия")
            return existing

        accrued_amount = None
        accrual_type = None
        if lesson_type == "paid" and status == "completed":
            prior_paid_lessons = await session.scalar(
                select(func.count(Lesson.id)).where(
                    Lesson.assignment_id == assignment_id,
                    Lesson.lesson_type == "paid",
                    Lesson.status == "completed",
                )
            )
            if (prior_paid_lessons or 0) + 1 >= assignment.short_term_lesson_limit:
                if assignment.payment_due_date is None:
                    assignment.payment_due_date = lesson_date
            if assignment.commission_mode == "percent":
                accrued_amount = (amount * assignment.commission_percentage / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                accrual_type = "lesson"
            elif (assignment.commission_mode != "subscription"
                    and (prior_paid_lessons or 0) + 1 == assignment.short_term_lesson_limit):
                accrued_amount = assignment.commission_amount
                accrual_type = "threshold"

        lesson = Lesson(
            assignment_id=assignment_id,
            lesson_date=lesson_date,
            lesson_type=lesson_type,
            status=status,
            amount=amount,
            operation_key=operation_key,
            notes=notes.strip() if notes else None,
        )
        session.add(lesson)
        if accrued_amount is not None:
            session.add(CommissionAccrual(
                assignment_id=assignment_id,
                lesson=lesson,
                event_type=accrual_type,
                amount=accrued_amount,
                operation_key=f"lesson:{sha256(operation_key.encode()).hexdigest()}",
            ))
        await session.commit()
        await session.refresh(lesson)
        return lesson
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(
            select(Lesson).where(Lesson.operation_key == operation_key)
        )
        if existing and (existing.assignment_id == assignment_id
                and existing.lesson_type == lesson_type and existing.status == status
                and existing.lesson_date == lesson_date and existing.amount == amount
                and (notes is None or existing.notes == notes)):
            return existing
        if existing:
            raise ValueError("Ключ операции уже использован для другого занятия") from error
        raise
    except Exception:
        await session.rollback()
        raise
