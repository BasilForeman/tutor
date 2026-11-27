from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Tutor


async def create_tutor(
    session: AsyncSession,
    nickname: str,
    subject: Optional[str] = None,
):
    if not isinstance(nickname, str):
        raise ValueError("Имя репетитора должно быть текстом")
    nickname = nickname.strip()

    if not nickname:
        raise ValueError("Имя репетитора не может быть пустым")

    existing = await session.scalar(
        select(Tutor).where(
            func.lower(Tutor.nickname) == nickname.lower(),
            Tutor.is_active.is_(True),
        )
    )

    if existing:
        raise ValueError("Такой репетитор уже существует")

    tutor = Tutor(
        nickname=nickname,
        subject=subject.strip() if subject else None,
    )

    try:
        session.add(tutor)
        await session.commit()
        await session.refresh(tutor)
    except IntegrityError as error:
        await session.rollback()
        raise ValueError("Такой репетитор уже существует") from error

    return tutor


async def get_tutors(session: AsyncSession, *, active_only: Optional[bool] = True,
                      search: Optional[str] = None):
    query = select(Tutor).order_by(Tutor.id)
    if active_only is True:
        query = query.where(Tutor.is_active.is_(True))
    elif active_only is False:
        query = query.where(Tutor.is_active.is_(False))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(Tutor.nickname.ilike(pattern) | Tutor.subject.ilike(pattern))
    result = await session.scalars(query)
    return list(result.all())


async def get_tutor_by_id(
    session: AsyncSession,
    tutor_id: int,
):
    return await session.get(Tutor, tutor_id)


async def check_tutor_exists(
    session: AsyncSession,
    nickname: str,
):
    result = await session.scalar(
        select(Tutor.id).where(
            func.lower(Tutor.nickname) == nickname.strip().lower(),
            Tutor.is_active.is_(True),
        )
    )
    return result is not None


async def update_tutor(session: AsyncSession, tutor_id: int, *, nickname: Optional[str] = None,
                       subject: Optional[str] = None) -> Optional[Tutor]:
    tutor = await session.get(Tutor, tutor_id)
    if not tutor or not tutor.is_active:
        return None
    if nickname is not None:
        nickname = nickname.strip()
        if not nickname:
            raise ValueError("Имя репетитора не может быть пустым")
        duplicate = await session.scalar(select(Tutor.id).where(
            func.lower(Tutor.nickname) == nickname.lower(), Tutor.id != tutor_id,
            Tutor.is_active.is_(True),
        ))
        if duplicate:
            raise ValueError("Такой репетитор уже существует")
        tutor.nickname = nickname
    if subject is not None:
        tutor.subject = subject.strip() or None
    try:
        await session.commit()
        await session.refresh(tutor)
    except IntegrityError as error:
        await session.rollback()
        raise ValueError("Такой репетитор уже существует") from error
    return tutor


async def archive_tutor(session: AsyncSession, tutor_id: int) -> bool:
    tutor = await session.get(Tutor, tutor_id)
    if not tutor or not tutor.is_active:
        return False
    tutor.is_active = False
    await session.commit()
    return True
