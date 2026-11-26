from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Client, Lead, LeadSource


LEAD_STATUSES = {
    "new",
    "in_progress",
    "assigned",
    "lost",
}


async def create_lead(
    session: AsyncSession,
    client_id: int,
    source_id: int,
    subject: Optional[str] = None,
    notes: Optional[str] = None,
) -> Lead:

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

    session.add(lead)
    await session.commit()
    await session.refresh(lead)

    return lead


async def get_leads(
    session: AsyncSession,
    status: Optional[str] = None,
):
    query = (
        select(Lead)
        .order_by(Lead.id.desc())
    )

    if status:
        query = query.where(Lead.status == status)

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
):

    if status not in LEAD_STATUSES:
        raise ValueError("Некорректный статус заявки")

    if status == "lost" and not (lost_reason or "").strip():
        raise ValueError("Укажите причину потери заявки")

    lead = await session.get(Lead, lead_id)

    if not lead:
        return None

    lead.status = status
    lead.lost_reason = lost_reason if status == "lost" else None

    await session.commit()
    await session.refresh(lead)

    return lead