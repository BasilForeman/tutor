
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Client


async def create_client(
    session: AsyncSession,
    nickname: str,
    contact: Optional[str] = None,
    notes: Optional[str] = None,
) -> Client:
    if not isinstance(nickname, str):
        raise ValueError("Имя ученика должно быть текстом")
    nickname = nickname.strip()

    if not nickname:
        raise ValueError("Имя ученика не может быть пустым")

    existing = await session.scalar(
        select(Client).where(
            func.lower(Client.nickname) == nickname.lower(),
            Client.is_active.is_(True),
        )
    )

    if existing:
        raise ValueError("Ученик с таким именем уже существует")

    client = Client(
        nickname=nickname,
        contact=contact.strip() if contact else None,
        notes=notes.strip() if notes else None,
    )

    try:
        session.add(client)
        await session.commit()
        await session.refresh(client)
    except IntegrityError as error:
        await session.rollback()
        raise ValueError("Ученик с таким именем уже существует") from error

    return client


async def get_clients(
    session: AsyncSession,
    active_only: Optional[bool] = True,
    search: Optional[str] = None,
) -> list[Client]:

    query = select(Client).order_by(Client.id.desc())

    if active_only is True:
        query = query.where(Client.is_active.is_(True))
    elif active_only is False:
        query = query.where(Client.is_active.is_(False))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            Client.nickname.ilike(pattern) | Client.contact.ilike(pattern)
            | Client.notes.ilike(pattern)
        )

    result = await session.scalars(query)

    return list(result.all())


async def get_client_by_id(
    session: AsyncSession,
    client_id: int,
) -> Optional[Client]:

    return await session.get(Client, client_id)


async def update_client(
    session: AsyncSession,
    client_id: int,
    nickname: Optional[str] = None,
    contact: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Client]:

    client = await session.get(Client, client_id)

    if not client or not client.is_active:
        return None

    if nickname is not None:
        nickname = nickname.strip()

        if not nickname:
            raise ValueError("Имя ученика не может быть пустым")

        existing = await session.scalar(
            select(Client).where(
                func.lower(Client.nickname) == nickname.lower(),
                Client.id != client_id,
                Client.is_active.is_(True),
            )
        )

        if existing:
            raise ValueError("Ученик с таким именем уже существует")

        client.nickname = nickname

    if contact is not None:
        client.contact = contact.strip() or None

    if notes is not None:
        client.notes = notes.strip() or None

    try:
        await session.commit()
        await session.refresh(client)
    except IntegrityError as error:
        await session.rollback()
        raise ValueError("Ученик с таким именем уже существует") from error

    return client


async def archive_client(
    session: AsyncSession,
    client_id: int,
) -> bool:

    client = await session.get(Client, client_id)

    if not client or not client.is_active:
        return False

    client.is_active = False

    await session.commit()

    return True
