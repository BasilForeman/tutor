from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from typing import Tuple

from sqlalchemy.exc import IntegrityError


SHORT_TERM_PERCENT = Decimal("0.25")
MONEY_QUANTUM = Decimal("0.01")


def short_term_commission(earnings: Decimal, lesson_count: int, lesson_limit: int = 4) -> Tuple[bool, Decimal]:
    """Return whether short-term settlement applies and the 25% amount."""
    if not isinstance(earnings, Decimal) or not earnings.is_finite() or earnings < 0:
        raise ValueError("Заработок должен быть конечным неотрицательным Decimal")
    if lesson_count < 0 or lesson_limit <= 0:
        raise ValueError("Количество занятий и порог заданы некорректно")
    if lesson_count > lesson_limit:
        return False, Decimal("0.00")
    amount = (earnings * SHORT_TERM_PERCENT).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    return True, amount


async def close_assignment(session, assignment_id, reason, author, operation_key):
    from sqlalchemy import func, select

    from bot.database.models import Assignment, AssignmentAdjustment, CommissionAccrual, Lesson

    if not all(isinstance(value, str) for value in (reason, author, operation_key)):
        raise ValueError("Причина, автор и ключ должны быть текстом")
    reason = reason.strip()
    author = author.strip()
    operation_key = operation_key.strip()
    if not reason:
        raise ValueError("Укажите причину завершения обучения")
    if not author:
        raise ValueError("Не удалось определить автора закрытия")
    if not operation_key or len(operation_key) > 128:
        raise ValueError("Не задан ключ операции закрытия")

    existing_assignment = await session.scalar(
        select(Assignment).where(Assignment.close_operation_key == operation_key)
    )
    if existing_assignment:
        if existing_assignment.id != assignment_id or existing_assignment.close_reason != reason or existing_assignment.closed_by != author:
            raise ValueError("Ключ операции уже использован для другого закрытия")
        adjustment = await session.scalar(
            select(AssignmentAdjustment).where(
                AssignmentAdjustment.operation_key == operation_key
            )
        )
        return existing_assignment, adjustment

    try:
        assignment = await session.scalar(
            select(Assignment)
            .where(Assignment.id == assignment_id)
            .with_for_update()
        )
        if not assignment:
            raise ValueError("Передача не найдена")
        if assignment.is_closed:
            raise ValueError("Передача уже закрыта")

        existing_assignment = await session.scalar(
            select(Assignment).where(Assignment.close_operation_key == operation_key)
        )
        if existing_assignment:
            if existing_assignment.id != assignment_id or existing_assignment.close_reason != reason or existing_assignment.closed_by != author:
                raise ValueError("Ключ операции уже использован для другого закрытия")
            adjustment = await session.scalar(
                select(AssignmentAdjustment).where(
                    AssignmentAdjustment.operation_key == operation_key
                )
            )
            return existing_assignment, adjustment

        lesson_stats = await session.execute(
            select(
                func.count(Lesson.id),
                func.coalesce(func.sum(Lesson.amount), 0),
            ).where(
                Lesson.assignment_id == assignment_id,
                Lesson.lesson_type == "paid",
                Lesson.status == "completed",
            )
        )
        lesson_count, earnings = lesson_stats.one()
        earnings = earnings or Decimal("0")
        # The 25% early-close rule is the default for the standard rate-multiplier
        # agreement. Preserve individually negotiated fixed/manual/subscription terms.
        commission_mode = getattr(assignment, "commission_mode", "rate_multiplier")
        if commission_mode == "rate_multiplier":
            within_limit, target_amount = short_term_commission(
                earnings,
                lesson_count,
                assignment.short_term_lesson_limit,
            )
        elif commission_mode == "percent":
            percent = assignment.commission_percentage
            target_amount = (earnings * percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            within_limit = True
        else:
            within_limit, target_amount = False, Decimal("0.00")

        previous_amount = assignment.commission_amount
        if commission_mode == "percent":
            previous_amount = await session.scalar(
                select(func.coalesce(func.sum(CommissionAccrual.amount), 0)).where(
                    CommissionAccrual.assignment_id == assignment_id
                )
            ) or Decimal("0")
        latest_adjustment = await session.scalar(
            select(AssignmentAdjustment)
            .where(AssignmentAdjustment.assignment_id == assignment_id)
            .order_by(AssignmentAdjustment.id.desc())
            .limit(1)
        )
        if latest_adjustment:
            previous_amount = latest_adjustment.new_amount

        if commission_mode in {"fixed", "manual"}:
            accrued_so_far = await session.scalar(
                select(func.coalesce(func.sum(CommissionAccrual.amount), 0)).where(
                    CommissionAccrual.assignment_id == assignment_id
                )
            ) or Decimal("0")
            if assignment.commission_amount > accrued_so_far:
                session.add(CommissionAccrual(
                    assignment_id=assignment_id,
                    event_type="closure",
                    amount=assignment.commission_amount - accrued_so_far,
                    operation_key=f"closure:{sha256(operation_key.encode()).hexdigest()}",
                ))

        adjustment = None
        if within_limit:
            if target_amount > 0 and assignment.payment_due_date is None:
                from datetime import date
                assignment.payment_due_date = date.today()
            if commission_mode == "percent":
                detail = (
                    f"{reason} | Комиссия {assignment.commission_percentage}% от заработка "
                    f"по {lesson_count} платным занятиям; заработок {earnings}"
                )
            else:
                detail = (
                    f"{reason} | Короткое обучение: {lesson_count} платных занятий, "
                    f"заработок {earnings}; комиссия 25%"
                )
            adjustment = AssignmentAdjustment(
                assignment_id=assignment_id,
                previous_amount=previous_amount,
                new_amount=target_amount,
                difference=target_amount - previous_amount,
                reason=detail,
                author=author,
                operation_key=operation_key,
            )
            session.add(adjustment)

        assignment.is_closed = True
        assignment.closed_at = func.current_timestamp()
        assignment.closed_by = author
        assignment.close_reason = reason
        assignment.close_operation_key = operation_key
        await session.commit()
        await session.refresh(assignment)
        return assignment, adjustment
    except Exception:
        await session.rollback()
        raise


async def adjust_assignment_commission(session, assignment_id, new_amount, reason, author, operation_key):
    from sqlalchemy import select, text
    from bot.database.models import Assignment, AssignmentAdjustment

    if not isinstance(new_amount, Decimal) or not new_amount.is_finite() or new_amount < 0:
        raise ValueError("Итоговая комиссия должна быть конечной неотрицательной Decimal")
    if not all(isinstance(value, str) for value in (reason, author, operation_key)):
        raise ValueError("Причина, автор и ключ должны быть текстом")
    reason = reason.strip()
    author = author.strip()
    operation_key = operation_key.strip()
    if not reason or not author or not operation_key or len(operation_key) > 128:
        raise ValueError("Укажите причину, автора и корректный ключ корректировки")

    existing = await session.scalar(select(AssignmentAdjustment).where(
        AssignmentAdjustment.operation_key == operation_key
    ))
    if existing:
        if (existing.assignment_id != assignment_id or existing.new_amount != new_amount
                or existing.reason != reason or existing.author != author):
            raise ValueError("Ключ операции уже использован для другой корректировки")
        return existing

    try:
        assignment = await session.scalar(
            select(Assignment).where(Assignment.id == assignment_id).with_for_update()
        )
        if not assignment:
            raise ValueError("Передача не найдена")
        existing = await session.scalar(select(AssignmentAdjustment).where(
            AssignmentAdjustment.operation_key == operation_key
        ))
        if existing:
            if (existing.assignment_id != assignment_id or existing.new_amount != new_amount
                    or existing.reason != reason or existing.author != author):
                raise ValueError("Ключ операции уже использован для другой корректировки")
            return existing
        current = await session.execute(text("""
            SELECT commission_amount FROM assignment_finances WHERE assignment_id = :assignment_id
        """), {"assignment_id": assignment_id})
        row = current.mappings().first()
        if not row:
            raise ValueError("Финансовое состояние передачи не найдено")
        previous_amount = row["commission_amount"]
        adjustment = AssignmentAdjustment(
            assignment_id=assignment_id,
            previous_amount=previous_amount,
            new_amount=new_amount,
            difference=new_amount - previous_amount,
            reason=reason,
            author=author,
            operation_key=operation_key,
        )
        session.add(adjustment)
        await session.commit()
        await session.refresh(adjustment)
        return adjustment
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(select(AssignmentAdjustment).where(
            AssignmentAdjustment.operation_key == operation_key
        ))
        if existing and (existing.assignment_id == assignment_id and existing.new_amount == new_amount
                and existing.reason == reason and existing.author == author):
            return existing
        if existing:
            raise ValueError("Ключ операции уже использован для другой корректировки") from error
        raise
    except Exception:
        await session.rollback()
        raise
