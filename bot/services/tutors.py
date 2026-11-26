from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Tutor


async def create_tutor(
    session: AsyncSession,
    nickname: str,
    subject: Optional[str] = None,
):
    nickname = nickname.strip()

    if not nickname:
        raise ValueError("Имя репетитора не может быть пустым")

    existing = await session.scalar(
        select(Tutor).where(
            func.lower(Tutor.nickname) == nickname.lower()
        )
    )

    if existing:
        raise ValueError("Такой репетитор уже существует")

    tutor = Tutor(
        nickname=nickname,
        subject=subject.strip() if subject else None,
    )

    session.add(tutor)
    await session.commit()
    await session.refresh(tutor)

    return tutor


async def get_tutors(session: AsyncSession):
    result = await session.scalars(
        select(Tutor).order_by(Tutor.id)
    )
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
            func.lower(Tutor.nickname) == nickname.strip().lower()
        )
    )
    return result is not None
