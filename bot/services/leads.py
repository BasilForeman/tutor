from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Client, Lead, LeadSource, LeadStatusHistory


LEAD_STATUSES = {
    "new",
    "in_progress",
    "assigned",
    "lost",
}

LEAD_TRANSITIONS = {
    "new": {"in_progress", "assigned", "lost"},
    "in_progress": {"assigned", "lost"},
    "assigned": {"in_progress", "lost"},
    "lost": {"in_progress"},  # explicit reopening
}


def record_lead_status_change(session: AsyncSession, lead: Lead, new_status: str, *,
                              changed_by: str = "system", reason: Optional[str] = None) -> None:
    """Apply a status change and append its history in the caller's transaction."""
    if new_status == lead.status:
        return
    if new_status not in LEAD_TRANSITIONS.get(lead.status, set()):
        raise ValueError(f"Недопустимый переход статуса: {lead.status} → {new_status}")
    session.add(LeadStatusHistory(
        lead_id=lead.id, old_status=lead.status, new_status=new_status,
        reason=_clean_optional(reason), changed_by=changed_by.strip() or "system",
    ))
    lead.status = new_status
    if new_status != "lost":
        lead.lost_reason = None


async def create_lead(
    session: AsyncSession,
    client_id: int,
    source_id: int,
    subject: Optional[str] = None,
    notes: Optional[str] = None,
    changed_by: str = "system",
) -> Lead:

    subject = _clean_optional(subject)
    notes = _clean_optional(notes)
    client = await session.get(Client, client_id)
    if not client or not client.is_active:
        raise ValueError("Активный ученик не найден")

    source = await session.get(LeadSource, source_id)
    if not source or not source.is_active:
        raise ValueError("Активный источник не найден")

    lead = Lead(
        client_id=client_id,
        source_id=source_id,
        subject=subject,
        notes=notes,
        status="new",
    )

    try:
        session.add(lead)
        session.add(LeadStatusHistory(
            lead=lead, old_status=None, new_status="new", reason="Создание заявки",
            changed_by=(changed_by or "").strip() or "system",
        ))
        await session.commit()
        await session.refresh(lead)
    except Exception:
        await session.rollback()
        raise

    return lead


async def get_leads(
    session: AsyncSession,
    status: Optional[str] = None,
    active_only: Optional[bool] = True,
    search: Optional[str] = None,
):
    query = (
        select(Lead)
        .order_by(Lead.id.desc())
    )

    if status:
        if status not in LEAD_STATUSES:
            raise ValueError("Некорректный статус заявки")
        query = query.where(Lead.status == status)

    if active_only is True:
        query = query.where(Lead.client.has(Client.is_active.is_(True)))
    elif active_only is False:
        query = query.where(Lead.client.has(Client.is_active.is_(False)))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.join(Client).where(
            Client.nickname.ilike(pattern)
            | Lead.subject.ilike(pattern)
            | Lead.notes.ilike(pattern)
        )

    result = await session.scalars(query)

    return list(result.all())


async def get_lead_by_id(
    session: AsyncSession,
    lead_id: int,
):
    return await session.get(Lead, lead_id)


async def update_lead_status(
    session: AsyncSession,
    lead_id: int,
    status: str,
    lost_reason: Optional[str] = None,
    changed_by: str = "telegram",
    reason: Optional[str] = None,
):

    if status not in LEAD_STATUSES:
        raise ValueError("Некорректный статус заявки")
    if status == "assigned":
        raise ValueError("Заявка получает статус «передана» при создании передачи")

    lost_reason = _clean_optional(lost_reason)
    reason = _clean_optional(reason) or lost_reason
    changed_by = (changed_by or "").strip()
    if not changed_by:
        raise ValueError("Укажите автора изменения статуса")
    if status == "lost" and not lost_reason:
        raise ValueError("Укажите причину потери заявки")

    lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())

    if not lead:
        return None

    if status == lead.status:
        if status == "lost" and lost_reason != lead.lost_reason:
            lead.lost_reason = lost_reason
            session.add(LeadStatusHistory(
                lead_id=lead.id, old_status=status, new_status=status,
                reason=reason, changed_by=changed_by,
            ))
        else:
            return lead
    else:
        if status not in LEAD_TRANSITIONS.get(lead.status, set()):
            raise ValueError(f"Недопустимый переход статуса: {lead.status} → {status}")
        record_lead_status_change(session, lead, status, changed_by=changed_by, reason=reason)
        lead.lost_reason = lost_reason if status == "lost" else None

    try:
        await session.commit()
        await session.refresh(lead)
    except Exception:
        await session.rollback()
        raise

    return lead


async def update_lead(
    session: AsyncSession, lead_id: int, *, client_id: Optional[int] = None,
    source_id: Optional[int] = None, subject: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Lead]:
    lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
    if not lead:
        return None
    if client_id is not None:
        client = await session.get(Client, client_id)
        if not client or not client.is_active:
            raise ValueError("Активный ученик не найден")
        lead.client_id = client_id
    if source_id is not None:
        source = await session.get(LeadSource, source_id)
        if not source or not source.is_active:
            raise ValueError("Активный источник не найден")
        lead.source_id = source_id
    if subject is not None:
        lead.subject = _clean_optional(subject)
    if notes is not None:
        lead.notes = _clean_optional(notes)
    try:
        await session.commit()
        await session.refresh(lead)
    except Exception:
        await session.rollback()
        raise
    return lead


async def get_lead_history(session: AsyncSession, lead_id: int):
    if not await session.get(Lead, lead_id):
        return None
    result = await session.scalars(
        select(LeadStatusHistory).where(LeadStatusHistory.lead_id == lead_id)
        .order_by(LeadStatusHistory.id)
    )
    return list(result.all())


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is not None and not isinstance(value, str):
        raise ValueError("Текстовое поле должно содержать текст")
    cleaned = value.strip() if value is not None else ""
    return cleaned or None
