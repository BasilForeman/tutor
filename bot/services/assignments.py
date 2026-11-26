
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Assignment,
    Lead,
    Tutor,
)


async def create_assignment(
    session: AsyncSession,
    lead_id: int,
    tutor_id: int,
    assigned_by: str,
    rate: Decimal,
    operation_key: str,
    commission_multiplier: Optional[Decimal] = None,
    commission_amount: Optional[Decimal] = None,
    assignment_date: Optional[date] = None,
    payment_due_date: Optional[date] = None,
    notes: Optional[str] = None,
) -> Assignment:
    """
    Создаёт передачу заявки репетитору.
    Client и LeadSource берутся непосредственно из Lead.
    """

    assigned_by = assigned_by.strip()

    if not assigned_by:
        raise ValueError("Необходимо указать, кто передал ученика")

    if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
        raise ValueError("Стоимость занятия должна быть конечным положительным Decimal")

    if commission_amount is not None and (
        not isinstance(commission_amount, Decimal)
        or not commission_amount.is_finite()
        or commission_amount < 0
    ):
        raise ValueError("Комиссия должна быть конечным неотрицательным Decimal")

    if commission_multiplier is None:
        commission_multiplier = Decimal("4")
    if (not isinstance(commission_multiplier, Decimal)
            or not commission_multiplier.is_finite()
            or commission_multiplier <= 0):
        raise ValueError("Множитель комиссии должен быть конечным положительным Decimal")

    calculated_commission = (rate * commission_multiplier).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if commission_amount is None:
        commission_amount = calculated_commission
    elif commission_amount != calculated_commission:
        raise ValueError("Сумма комиссии не совпадает с множителем ставки")

    operation_key = (operation_key or "").strip()
    if not operation_key or len(operation_key) > 128:
        raise ValueError("Не задан корректный ключ операции передачи")

    existing = await session.scalar(
        select(Assignment).where(Assignment.operation_key == operation_key)
    )
    if existing:
        if (existing.lead_id != lead_id or existing.tutor_id != tutor_id
                or existing.rate != rate or existing.commission_amount != commission_amount
                or getattr(existing, "commission_multiplier", commission_multiplier) != commission_multiplier
                or existing.assigned_by != assigned_by
                or (assignment_date is not None and existing.assignment_date != assignment_date)
                or (payment_due_date is not None and existing.payment_due_date != payment_due_date)):
            raise ValueError("Ключ операции уже использован для другой передачи")
        return existing

    lead = await session.scalar(
        select(Lead).where(Lead.id == lead_id).with_for_update()
    )

    if not lead:
        raise ValueError("Заявка не найдена")

    if lead.status == "lost":
        raise ValueError("Нельзя передать потерянную заявку")

    # Recheck after locking the lead so retries of this operation serialize.
    existing = await session.scalar(
        select(Assignment).where(Assignment.operation_key == operation_key)
    )
    if existing:
        if (existing.lead_id != lead_id or existing.tutor_id != tutor_id
                or existing.rate != rate or existing.commission_amount != commission_amount
                or getattr(existing, "commission_multiplier", commission_multiplier) != commission_multiplier
                or existing.assigned_by != assigned_by
                or (assignment_date is not None and existing.assignment_date != assignment_date)
                or (payment_due_date is not None and existing.payment_due_date != payment_due_date)):
            raise ValueError("Ключ операции уже использован для другой передачи")
        return existing

    tutor = await session.get(Tutor, tutor_id)

    if not tutor:
        raise ValueError("Репетитор не найден")

    assignment = Assignment(
        assignment_date=assignment_date or date.today(),
        tutor_id=tutor.id,
        client_id=lead.client_id,
        lead_id=lead.id,
        source_id=lead.source_id,
        assigned_by=assigned_by,
        rate=rate,
        commission_amount=commission_amount,
        commission_multiplier=commission_multiplier,
        operation_key=operation_key,
        payment_due_date=payment_due_date,
        notes=notes.strip() if notes else None,
    )

    try:
        session.add(assignment)

        # Меняем статус заявки в той же транзакции
        lead.status = "assigned"

        await session.commit()
        await session.refresh(assignment)

        return assignment

    except Exception:
        await session.rollback()
        raise


async def get_assignments(
    session: AsyncSession,
    tutor_id: Optional[int] = None,
    client_id: Optional[int] = None,
    lead_id: Optional[int] = None,
):
    query = select(Assignment).order_by(
        Assignment.id.desc()
    )

    if tutor_id is not None:
        query = query.where(
            Assignment.tutor_id == tutor_id
        )

    if client_id is not None:
        query = query.where(
            Assignment.client_id == client_id
        )

    if lead_id is not None:
        query = query.where(
            Assignment.lead_id == lead_id
        )

    result = await session.scalars(query)

    return list(result.all())


async def get_assignment_by_id(
    session: AsyncSession,
    assignment_id: int,
):
    return await session.get(Assignment, assignment_id)
