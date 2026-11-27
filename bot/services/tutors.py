from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

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


async def get_tutor_profile(session: AsyncSession, tutor_id: int) -> Optional[dict]:
    """Read-only tutor metrics, assignment history, and parent payment history."""
    from bot.services.tutor_payments import get_tutor_payment_history

    result = await session.execute(text("""SELECT t.id,t.nickname,t.subject,t.is_active,
        COUNT(a.id) AS assignments,
        COUNT(a.id) FILTER (WHERE NOT a.is_closed) AS active_assignments,
        COUNT(a.id) FILTER (WHERE a.is_closed) AS closed_assignments,
        (SELECT COUNT(*) FROM lessons l JOIN assignments al ON al.id=l.assignment_id
          WHERE al.tutor_id=t.id AND l.status='completed') AS completed_lessons,
        (SELECT COUNT(*) FROM lessons l JOIN assignments al ON al.id=l.assignment_id
          WHERE al.tutor_id=t.id AND l.status='completed' AND l.lesson_type='trial') AS trial_lessons,
        (SELECT COUNT(*) FROM lessons l JOIN assignments al ON al.id=l.assignment_id
          WHERE al.tutor_id=t.id AND l.status='completed' AND l.lesson_type='paid') AS paid_lessons,
        COALESCE(SUM(f.commission_amount),0) AS commission,
        COALESCE(SUM(f.paid_amount),0) AS paid,
        COALESCE(SUM(GREATEST(f.remaining_amount,0)),0) AS debt,
        (SELECT COUNT(*) FROM payment_refunds r JOIN payments p ON p.id=r.payment_id
          JOIN assignments ar ON ar.id=p.assignment_id WHERE ar.tutor_id=t.id) AS refund_count,
        (SELECT COALESCE(SUM(r.amount),0) FROM payment_refunds r JOIN payments p ON p.id=r.payment_id
          JOIN assignments ar ON ar.id=p.assignment_id WHERE ar.tutor_id=t.id) AS refunds
        FROM tutors t
        LEFT JOIN assignments a ON a.tutor_id=t.id
        LEFT JOIN assignment_finances f ON f.assignment_id=a.id
        WHERE t.id=:tutor_id
        GROUP BY t.id,t.nickname,t.subject,t.is_active"""), {"tutor_id": tutor_id})
    row = result.mappings().first()
    if not row:
        return None
    assignment_result = await session.execute(text("""SELECT a.id,a.assignment_date,c.nickname AS client,
        a.is_closed,a.closed_at,a.close_reason,f.commission_amount,f.paid_amount,f.remaining_amount,
        COUNT(l.id) FILTER (WHERE l.status='completed') AS completed_lessons,
        COUNT(l.id) FILTER (WHERE l.status='completed' AND l.lesson_type='trial') AS trial_lessons,
        COUNT(l.id) FILTER (WHERE l.status='completed' AND l.lesson_type='paid') AS paid_lessons
        FROM assignments a JOIN clients c ON c.id=a.client_id
        LEFT JOIN assignment_finances f ON f.assignment_id=a.id
        LEFT JOIN lessons l ON l.assignment_id=a.id
        WHERE a.tutor_id=:tutor_id
        GROUP BY a.id,c.nickname,f.commission_amount,f.paid_amount,f.remaining_amount
        ORDER BY a.assignment_date DESC,a.id DESC LIMIT 30"""), {"tutor_id": tutor_id})
    assignments = [dict(item) for item in assignment_result.mappings().all()]
    payments = await get_tutor_payment_history(session, tutor_id, limit=10)
    return {"summary": dict(row), "assignments": assignments, "payments": payments}
