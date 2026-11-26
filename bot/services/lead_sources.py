
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import LeadSource


async def create_lead_source(
    session: AsyncSession,
    name: str,
) -> LeadSource:
    name = name.strip()

    if not name:
        raise ValueError("Название источника не может быть пустым")

    existing = await session.scalar(
        select(LeadSource).where(
            func.lower(LeadSource.name) == name.lower(),
            LeadSource.is_active.is_(True),
        )
    )

    if existing:
        raise ValueError("Такой источник уже существует")

    source = LeadSource(name=name)

    session.add(source)
    await session.commit()
    await session.refresh(source)

    return source


async def get_lead_sources(
    session: AsyncSession,
    active_only: bool = True,
) -> list[LeadSource]:

    query = select(LeadSource).order_by(LeadSource.id)

    if active_only:
        query = query.where(LeadSource.is_active.is_(True))

    result = await session.scalars(query)

    return list(result.all())


async def get_lead_source_by_id(
    session: AsyncSession,
    source_id: int,
):
    return await session.get(LeadSource, source_id)


async def archive_lead_source(
    session: AsyncSession,
    source_id: int,
) -> bool:

    source = await session.get(LeadSource, source_id)

    if not source or not source.is_active:
        return False

    source.is_active = False

    await session.commit()

    return True
