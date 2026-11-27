
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Assignment,
    CommissionAccrual,
    Client,
    Lead,
    LeadSource,
    LeadStatusHistory,
    Tutor,
)
from bot.services.leads import record_lead_status_change


async def create_manual_assignment(
    session: AsyncSession, *, tutor_name: str, tutor_subject: Optional[str],
    client_name: str, client_contact: Optional[str], source_name: str,
    subject: Optional[str], assigned_by: str, rate: Decimal, operation_key: str,
    commission_multiplier: Optional[Decimal] = None,
    commission_amount: Optional[Decimal] = None,
    commission_mode: str = "rate_multiplier",
    commission_percentage: Optional[Decimal] = None,
    subscription_purchase_date: Optional[date] = None,
    payment_due_date: Optional[date] = None,
):
    """Resolve or create the entities for a manually entered assignment atomically."""
    tutor_name = _required_text(tutor_name, "Имя репетитора")
    client_name = _required_text(client_name, "Имя ученика")
    source_name = _required_text(source_name, "Источник заявки")
    tutor_subject = _optional_text(tutor_subject)
    client_contact = _optional_text(client_contact)
    subject = _optional_text(subject)
    created = {"tutor": False, "client": False, "source": False, "lead": False}

    try:
        tutor = await session.scalar(select(Tutor).where(
            func.lower(func.btrim(Tutor.nickname)) == tutor_name.lower(),
            Tutor.is_active.is_(True),
        ).order_by(Tutor.id).limit(1))
        if tutor is None:
            tutor = Tutor(nickname=tutor_name, subject=tutor_subject)
            session.add(tutor)
            await session.flush()
            created["tutor"] = True

        client = await session.scalar(select(Client).where(
            func.lower(func.btrim(Client.nickname)) == client_name.lower(),
            Client.is_active.is_(True),
        ).order_by(Client.id).limit(1))
        if client is None:
            client = Client(nickname=client_name, contact=client_contact)
            session.add(client)
            await session.flush()
            created["client"] = True

        source = await session.scalar(select(LeadSource).where(
            func.lower(func.btrim(LeadSource.name)) == source_name.lower(),
            LeadSource.is_active.is_(True),
        ).order_by(LeadSource.id).limit(1))
        if source is None:
            source = LeadSource(name=source_name)
            session.add(source)
            await session.flush()
            created["source"] = True

        lead_query = select(Lead).where(
            Lead.client_id == client.id,
            Lead.source_id == source.id,
            Lead.status != "lost",
        )
        if subject is None:
            lead_query = lead_query.where(Lead.subject.is_(None))
        else:
            lead_query = lead_query.where(
                func.lower(func.btrim(Lead.subject)) == subject.lower()
            )
        lead = await session.scalar(lead_query.order_by(Lead.id.desc()).limit(1))
        if lead is None:
            lead = Lead(client_id=client.id, source_id=source.id, subject=subject, status="new")
            session.add(lead)
            await session.flush()
            session.add(LeadStatusHistory(
                lead_id=lead.id, old_status=None, new_status="new",
                reason="Создание заявки при ручном оформлении передачи",
                changed_by=assigned_by.strip() or "Sonya",
            ))
            created["lead"] = True

        assignment = await create_assignment(
            session=session, lead_id=lead.id, tutor_id=tutor.id,
            assigned_by=assigned_by, rate=rate, operation_key=operation_key,
            commission_multiplier=commission_multiplier,
            commission_amount=commission_amount, commission_mode=commission_mode,
            commission_percentage=commission_percentage,
            subscription_purchase_date=subscription_purchase_date,
            payment_due_date=payment_due_date,
        )
        return assignment, created
    except Exception:
        await session.rollback()
        raise


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} не может быть пустым")
    return value.strip()


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is not None and not isinstance(value, str):
        raise ValueError("Дополнительные данные должны быть текстом")
    return value.strip() or None if value is not None else None


async def create_assignment(
    session: AsyncSession,
    lead_id: int,
    tutor_id: int,
    assigned_by: str,
    rate: Decimal,
    operation_key: str,
    commission_multiplier: Optional[Decimal] = None,
    commission_amount: Optional[Decimal] = None,
    commission_mode: str = "rate_multiplier",
    commission_percentage: Optional[Decimal] = None,
    subscription_purchase_date: Optional[date] = None,
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

    if commission_mode not in {"rate_multiplier", "fixed", "manual", "subscription", "percent"}:
        raise ValueError("Неизвестный режим комиссии")
    if commission_mode == "percent":
        if (not isinstance(commission_percentage, Decimal)
                or not commission_percentage.is_finite()
                or commission_percentage <= 0 or commission_percentage > 100):
            raise ValueError("Процент комиссии должен быть больше 0 и не больше 100")
        if commission_amount not in (None, Decimal("0")):
            raise ValueError("В режиме процента сумма комиссии рассчитывается из заработка")
        commission_amount = Decimal("0.00")
    elif commission_percentage is not None:
        raise ValueError("Процент указывается только в процентном режиме")
    if commission_mode == "subscription":
        if subscription_purchase_date is None:
            raise ValueError("Для абонемента укажите дату покупки")
        if not isinstance(subscription_purchase_date, date):
            raise ValueError("Некорректная дата покупки абонемента")
    elif subscription_purchase_date is not None:
        raise ValueError("Дата покупки указывается только для режима абонемента")

    if commission_multiplier is None:
        commission_multiplier = Decimal("4")
    if (not isinstance(commission_multiplier, Decimal)
            or not commission_multiplier.is_finite()
            or commission_multiplier <= 0):
        raise ValueError("Множитель комиссии должен быть конечным положительным Decimal")

    if commission_mode == "rate_multiplier":
        calculated_commission = (rate * commission_multiplier).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if commission_amount is None:
            commission_amount = calculated_commission
        elif commission_amount != calculated_commission:
            raise ValueError("Сумма комиссии не совпадает с множителем ставки")
    elif commission_amount is None:
        raise ValueError("Для выбранного режима укажите согласованную сумму комиссии")

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
                or getattr(existing, "commission_mode", commission_mode) != commission_mode
                or getattr(existing, "commission_percentage", commission_percentage) != commission_percentage
                or getattr(existing, "subscription_purchase_date", subscription_purchase_date) != subscription_purchase_date
                or existing.assigned_by != assigned_by
                or (assignment_date is not None and existing.assignment_date != assignment_date)
                or (payment_due_date is not None and existing.payment_due_date != payment_due_date)
                or (notes is not None and existing.notes != notes)):
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
                or getattr(existing, "commission_mode", commission_mode) != commission_mode
                or getattr(existing, "commission_percentage", commission_percentage) != commission_percentage
                or getattr(existing, "subscription_purchase_date", subscription_purchase_date) != subscription_purchase_date
                or existing.assigned_by != assigned_by
                or (assignment_date is not None and existing.assignment_date != assignment_date)
                or (payment_due_date is not None and existing.payment_due_date != payment_due_date)
                or (notes is not None and existing.notes != notes)):
            raise ValueError("Ключ операции уже использован для другой передачи")
        return existing

    tutor = await session.get(Tutor, tutor_id)

    if not tutor or not tutor.is_active:
        raise ValueError("Активный репетитор не найден")
    client = await session.get(Client, lead.client_id)
    source = await session.get(LeadSource, lead.source_id)
    if not client or not client.is_active:
        raise ValueError("Ученик заявки неактивен или не найден")
    if not source or not source.is_active:
        raise ValueError("Источник заявки неактивен или не найден")

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
        commission_mode=commission_mode,
        commission_percentage=commission_percentage,
        subscription_purchase_date=subscription_purchase_date,
        operation_key=operation_key,
        payment_due_date=payment_due_date,
        notes=notes.strip() if notes else None,
    )

    try:
        session.add(assignment)
        if commission_mode == "subscription":
            session.add(CommissionAccrual(
                assignment=assignment,
                event_type="subscription",
                amount=commission_amount,
                operation_key=f"subscription:{sha256(operation_key.encode()).hexdigest()}",
            ))

        # Меняем статус заявки в той же транзакции
        record_lead_status_change(
            session, lead, "assigned", changed_by=assigned_by,
            reason=f"Передана репетитору ID {tutor.id}",
        )

        await session.commit()
        await session.refresh(assignment)

        return assignment

    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(
            select(Assignment).where(Assignment.operation_key == operation_key)
        )
        if existing:
            if (existing.lead_id == lead_id and existing.tutor_id == tutor_id
                    and existing.rate == rate and existing.commission_amount == commission_amount
                    and existing.commission_multiplier == commission_multiplier
                    and existing.commission_mode == commission_mode
                    and existing.commission_percentage == commission_percentage
                    and existing.subscription_purchase_date == subscription_purchase_date
                    and existing.assigned_by == assigned_by
                    and (assignment_date is None or existing.assignment_date == assignment_date)
                    and (payment_due_date is None or existing.payment_due_date == payment_due_date)
                    and (notes is None or existing.notes == notes)):
                return existing
            raise ValueError("Ключ операции уже использован для другой передачи") from error
        raise
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
