from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Assignment, Payment, Tutor, TutorPaymentBatch


def parse_allocation_lines(value: str) -> list[tuple[int, Decimal]]:
    """Parse one assignment_id=amount allocation per line; decimal comma is accepted."""
    allocations = []
    seen = set()
    for raw_line in (value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError("Каждую строку введи как «ID передачи = сумма»")
        raw_id, raw_amount = (part.strip() for part in line.split("=", 1))
        try:
            assignment_id = int(raw_id)
            amount = Decimal(raw_amount.replace(",", "."))
        except (ValueError, InvalidOperation):
            raise ValueError("Проверь ID передачи и сумму в распределении") from None
        if assignment_id <= 0 or not amount.is_finite() or amount <= 0:
            raise ValueError("ID должен быть положительным, сумма — конечной и больше нуля")
        if assignment_id in seen:
            raise ValueError(f"Передача №{assignment_id} указана дважды")
        seen.add(assignment_id)
        allocations.append((assignment_id, amount))
    if not allocations:
        raise ValueError("Добавь хотя бы одну строку распределения")
    return allocations


async def get_tutors_for_payments(session: AsyncSession):
    result = await session.execute(text("""SELECT t.id,t.nickname,t.is_active,
        COALESCE((SELECT SUM(GREATEST(f.remaining_amount,0)) FROM assignments a
          JOIN assignment_finances f ON f.assignment_id=a.id WHERE a.tutor_id=t.id),0) AS debt,
        COALESCE((SELECT SUM(GREATEST(b.amount-COALESCE(x.allocated,0),0)) FROM payment_batches b
          LEFT JOIN (SELECT payment_batch_id,SUM(amount) AS allocated FROM payments GROUP BY payment_batch_id) x
            ON x.payment_batch_id=b.id WHERE b.tutor_id=t.id),0) AS advance
        FROM tutors t ORDER BY debt DESC,advance DESC,lower(t.nickname),t.id"""))
    return list(result.mappings().all())


async def get_tutor_outstanding_assignments(session: AsyncSession, tutor_id: int):
    result = await session.execute(text("""SELECT a.id AS assignment_id,a.assignment_date,
        a.client_id,c.nickname AS client,c.contact AS client_contact,a.tutor_id,t.nickname AS tutor,
        a.commission_mode,a.commission_multiplier,a.commission_percentage,
        f.commission_amount,f.agreed_commission,f.paid_amount,f.remaining_amount,
        COALESCE(ls.paid_lessons,0) AS paid_lessons
        FROM assignments a JOIN clients c ON c.id=a.client_id
        JOIN tutors t ON t.id=a.tutor_id
        JOIN assignment_finances f ON f.assignment_id=a.id
        LEFT JOIN (SELECT assignment_id,COUNT(*) AS paid_lessons FROM lessons
          WHERE lesson_type='paid' AND status='completed' GROUP BY assignment_id) ls ON ls.assignment_id=a.id
        WHERE a.tutor_id=:tutor_id AND f.remaining_amount > 0
        ORDER BY a.assignment_date, a.id"""), {"tutor_id": tutor_id})
    return list(result.mappings().all())


async def get_tutor_payment_history(session: AsyncSession, tutor_id: int, limit: int = 20):
    result = await session.execute(text("""SELECT b.id,b.tutor_id,t.nickname AS tutor,
        b.payment_date,b.amount,b.notes,COALESCE(SUM(p.amount),0) AS allocated,
        GREATEST(b.amount-COALESCE(SUM(p.amount),0),0) AS advance
        FROM payment_batches b LEFT JOIN payments p ON p.payment_batch_id=b.id
        JOIN tutors t ON t.id=b.tutor_id
        WHERE b.tutor_id=:tutor_id
        GROUP BY b.id,t.nickname ORDER BY b.payment_date DESC, b.id DESC LIMIT :limit"""),
        {"tutor_id": tutor_id, "limit": limit})
    batches = list(result.mappings().all())
    history = []
    for batch in batches:
        parts = await session.execute(text("""SELECT p.assignment_id,c.nickname AS client,c.contact AS client_contact,
            t.nickname AS tutor,p.payment_date AS allocation_date,p.amount,p.notes,
            COALESCE(SUM(r.amount),0) AS refunded
            FROM payments p JOIN assignments a ON a.id=p.assignment_id
            JOIN clients c ON c.id=a.client_id
            JOIN tutors t ON t.id=a.tutor_id
            LEFT JOIN payment_refunds r ON r.payment_id=p.id
            WHERE p.payment_batch_id=:batch_id
            GROUP BY p.id,p.assignment_id,c.nickname,c.contact,t.nickname ORDER BY p.payment_date,p.id"""),
            {"batch_id": batch["id"]})
        history.append({"batch": dict(batch), "allocations": list(parts.mappings().all())})
    return history


def _allocation_key(operation_key: str, assignment_id: int) -> str:
    return "batch-allocation:" + sha256(f"{operation_key}:{assignment_id}".encode()).hexdigest()


async def _existing_batch(session, batch, tutor_id, amount, allocations, payment_date, notes):
    result = await session.scalars(select(Payment).where(
        Payment.payment_batch_id == batch.id
    ).order_by(Payment.assignment_id))
    rows = list(result.all())
    expected_date = payment_date or date.today()
    original_rows = [row for row in rows if row.operation_key == _allocation_key(batch.operation_key, row.assignment_id)]
    if (batch.tutor_id != tutor_id or batch.amount != amount
            or batch.payment_date != expected_date or batch.notes != notes
            or [(row.assignment_id, row.amount) for row in original_rows] != allocations):
        raise ValueError("Ключ операции уже использован для другого платежа")
    return batch, rows


async def create_tutor_payment_batch(
    session: AsyncSession, *, tutor_id: int, amount: Decimal,
    allocations: list[tuple[int, Decimal]], operation_key: str,
    payment_date: date | None = None, notes: str | None = None,
    allow_advance: bool = False,
):
    """Save one received payment and all its per-assignment allocations atomically."""
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
        raise ValueError("Сумма платежа должна быть конечным положительным Decimal")
    if not isinstance(tutor_id, int) or isinstance(tutor_id, bool) or tutor_id <= 0:
        raise ValueError("Некорректный ID репетитора")
    if not isinstance(operation_key, str):
        raise ValueError("Не задан ключ операции платежа")
    operation_key = operation_key.strip()
    if not operation_key or len(operation_key) > 128:
        raise ValueError("Не задан корректный ключ операции платежа")
    if payment_date is not None and not isinstance(payment_date, date):
        raise ValueError("Некорректная дата платежа")
    payment_date = payment_date or date.today()
    if notes is not None and not isinstance(notes, str):
        raise ValueError("Комментарий должен быть текстом")
    notes = notes.strip() or None if notes is not None else None
    if not isinstance(allow_advance, bool):
        raise ValueError("Некорректное подтверждение аванса")

    normalized = []
    seen = set()
    for assignment_id, allocation in allocations:
        if not isinstance(assignment_id, int) or isinstance(assignment_id, bool) or assignment_id <= 0:
            raise ValueError("Некорректный ID передачи в распределении")
        if assignment_id in seen:
            raise ValueError("Передача указана в распределении дважды")
        if not isinstance(allocation, Decimal) or not allocation.is_finite() or allocation <= 0:
            raise ValueError("Каждая часть платежа должна быть конечной суммой больше нуля")
        seen.add(assignment_id)
        normalized.append((assignment_id, allocation))
    normalized.sort(key=lambda item: item[0])
    allocated_total = sum((value for _, value in normalized), Decimal("0"))
    if allocated_total > amount:
        raise ValueError("Сумма распределений не может быть больше полученного платежа")
    if allocated_total < amount and not allow_advance:
        raise ValueError("Сумма распределений должна совпадать с платежом, если аванс отдельно не подтверждён")

    try:
        batch = await session.scalar(select(TutorPaymentBatch).where(
            TutorPaymentBatch.operation_key == operation_key
        ))
        if batch:
            return await _existing_batch(session, batch, tutor_id, amount, normalized, payment_date, notes)

        tutor = await session.scalar(select(Tutor).where(
            Tutor.id == tutor_id
        ).with_for_update())
        if not tutor:
            raise ValueError("Репетитор не найден")
        batch = await session.scalar(select(TutorPaymentBatch).where(
            TutorPaymentBatch.operation_key == operation_key
        ))
        if batch:
            return await _existing_batch(session, batch, tutor_id, amount, normalized, payment_date, notes)

        found = await session.scalars(select(Assignment).where(
            Assignment.id.in_(seen), Assignment.tutor_id == tutor_id
        ).order_by(Assignment.id).with_for_update())
        assignments = list(found.all())
        if len(assignments) != len(seen):
            raise ValueError("Одна из передач не принадлежит выбранному репетитору")

        for assignment_id, allocation in normalized:
            finance = await session.execute(text("""SELECT remaining_amount
                FROM assignment_finances WHERE assignment_id=:assignment_id"""),
                {"assignment_id": assignment_id})
            row = finance.mappings().first()
            if not row or row["remaining_amount"] <= 0:
                raise ValueError(f"По передаче №{assignment_id} нет долга для оплаты")
            if allocation > row["remaining_amount"]:
                raise ValueError(
                    f"Распределение {allocation} превышает долг по передаче №{assignment_id}: "
                    f"{row['remaining_amount']}"
                )

        batch = TutorPaymentBatch(
            tutor_id=tutor_id, payment_date=payment_date, amount=amount,
            notes=notes, operation_key=operation_key,
        )
        session.add(batch)
        await session.flush()
        for assignment_id, allocation in normalized:
            session.add(Payment(
                payment_batch_id=batch.id,
                assignment_id=assignment_id,
                payment_date=payment_date,
                amount=allocation,
                notes=notes,
                operation_key=_allocation_key(operation_key, assignment_id),
            ))
        await session.commit()
        await session.refresh(batch)
        rows = await session.scalars(select(Payment).where(
            Payment.payment_batch_id == batch.id
        ).order_by(Payment.assignment_id))
        return batch, list(rows.all())
    except IntegrityError as error:
        await session.rollback()
        batch = await session.scalar(select(TutorPaymentBatch).where(
            TutorPaymentBatch.operation_key == operation_key
        ))
        if batch:
            try:
                return await _existing_batch(session, batch, tutor_id, amount,
                                             normalized, payment_date, notes)
            except ValueError as mismatch:
                raise mismatch from error
        raise
    except Exception:
        await session.rollback()
        raise


async def get_tutor_advances(session: AsyncSession, tutor_id: int):
    result = await session.execute(text("""SELECT b.id AS batch_id,b.tutor_id,t.nickname AS tutor,
        b.payment_date,b.amount AS received,b.notes,
        COALESCE(SUM(p.amount),0) AS allocated,
        GREATEST(b.amount-COALESCE(SUM(p.amount),0),0) AS available
        FROM payment_batches b JOIN tutors t ON t.id=b.tutor_id
        LEFT JOIN payments p ON p.payment_batch_id=b.id
        WHERE b.tutor_id=:tutor_id
        GROUP BY b.id,t.nickname
        HAVING b.amount-COALESCE(SUM(p.amount),0)>0
        ORDER BY b.payment_date,b.id"""), {"tutor_id": tutor_id})
    return list(result.mappings().all())


async def allocate_tutor_advance(
    session: AsyncSession, *, tutor_id: int, batch_id: int,
    allocations: list[tuple[int, Decimal]], operation_key: str,
):
    """Apply part of one previously received batch to current assignment debts atomically."""
    if not isinstance(operation_key, str) or not operation_key.strip() or len(operation_key.strip()) > 128:
        raise ValueError("Не задан корректный ключ операции распределения аванса")
    operation_key = operation_key.strip()
    if not allocations:
        raise ValueError("Добавь хотя бы одно распределение аванса")
    normalized = []
    seen = set()
    for assignment_id, amount in allocations:
        if not isinstance(assignment_id, int) or isinstance(assignment_id, bool) or assignment_id <= 0:
            raise ValueError("Некорректный ID передачи")
        if assignment_id in seen:
            raise ValueError("Передача указана несколько раз в одном распределении")
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
            raise ValueError("Сумма распределения должна быть конечной и больше нуля")
        seen.add(assignment_id)
        normalized.append((assignment_id, amount))
    normalized.sort(key=lambda item: item[0])
    operation_keys = {assignment_id: _allocation_key("advance:" + operation_key, assignment_id)
                      for assignment_id, _ in normalized}
    if sum((amount for _, amount in normalized), Decimal("0")) <= 0:
        raise ValueError("Добавь положительную сумму распределения")

    try:
        tutor = await session.scalar(select(Tutor).where(Tutor.id == tutor_id).with_for_update())
        if not tutor:
            raise ValueError("Репетитор не найден")
        batch = await session.scalar(select(TutorPaymentBatch).where(
            TutorPaymentBatch.id == batch_id, TutorPaymentBatch.tutor_id == tutor_id
        ).with_for_update())
        if not batch:
            raise ValueError("Аванс этого репетитора не найден")
        assignments_result = await session.scalars(select(Assignment).where(
            Assignment.id.in_(seen), Assignment.tutor_id == tutor_id
        ).order_by(Assignment.id).with_for_update())
        assignments_found = list(assignments_result.all())
        if len(assignments_found) != len(seen):
            raise ValueError("Одна из передач не принадлежит выбранному репетитору")

        existing_rows = list((await session.scalars(select(Payment).where(
            Payment.operation_key.in_(list(operation_keys.values()))
        ))).all())
        if existing_rows:
            actual = sorted((row.assignment_id, row.amount) for row in existing_rows)
            if (len(existing_rows) != len(normalized)
                    or any(row.payment_batch_id != batch_id for row in existing_rows)
                    or actual != normalized):
                raise ValueError("Ключ операции уже использован для другого распределения")
            return existing_rows

        allocated = await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.payment_batch_id == batch_id
        )) or Decimal("0")
        available = batch.amount - allocated
        requested = sum((amount for _, amount in normalized), Decimal("0"))
        if requested > available:
            raise ValueError(f"Сумма превышает доступный аванс {available}")
        for assignment_id, amount in normalized:
            finance = await session.execute(text("""SELECT remaining_amount FROM assignment_finances
                WHERE assignment_id=:assignment_id"""), {"assignment_id": assignment_id})
            row = finance.mappings().first()
            if not row or row["remaining_amount"] <= 0:
                raise ValueError(f"По передаче №{assignment_id} нет долга для распределения аванса")
            if amount > row["remaining_amount"]:
                raise ValueError(f"Сумма {amount} превышает долг по передаче №{assignment_id}: {row['remaining_amount']}")
            session.add(Payment(
                payment_batch_id=batch_id, assignment_id=assignment_id,
                payment_date=date.today(), amount=amount,
                notes="Распределение ранее полученного аванса",
                operation_key=operation_keys[assignment_id],
            ))
        await session.commit()
        result = await session.scalars(select(Payment).where(
            Payment.operation_key.in_(list(operation_keys.values()))
        ).order_by(Payment.assignment_id))
        return list(result.all())
    except IntegrityError:
        await session.rollback()
        existing_rows = list((await session.scalars(select(Payment).where(
            Payment.operation_key.in_(list(operation_keys.values()))
        ))).all())
        if (len(existing_rows) == len(normalized)
                and all(row.payment_batch_id == batch_id for row in existing_rows)
                and sorted((row.assignment_id, row.amount) for row in existing_rows) == normalized):
            return existing_rows
        raise
    except Exception:
        await session.rollback()
        raise
