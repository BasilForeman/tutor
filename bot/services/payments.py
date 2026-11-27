from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Assignment, Payment, PaymentRefund


async def create_payment(
    session: AsyncSession,
    assignment_id: int,
    amount: Decimal,
    operation_key: str,
    payment_date: Optional[date] = None,
    notes: Optional[str] = None,
) -> Payment:
    """Create an idempotent partial/full commission payment."""
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
        raise ValueError("Сумма платежа должна быть конечным положительным Decimal")

    operation_key = (operation_key or "").strip()
    if not operation_key or len(operation_key) > 128:
        raise ValueError("Не задан корректный ключ операции платежа")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("Комментарий должен быть текстом")
    notes = notes.strip() if notes else None

    existing = await session.scalar(
        select(Payment).where(Payment.operation_key == operation_key)
    )
    if existing:
        if (existing.assignment_id != assignment_id or existing.amount != amount
                or (payment_date is not None and existing.payment_date != payment_date)
                or (notes is not None and existing.notes != notes)):
            raise ValueError("Ключ операции уже использован для другого платежа")
        return existing

    try:
        assignment = await session.scalar(
            select(Assignment)
            .where(Assignment.id == assignment_id)
            .with_for_update()
        )
        if not assignment:
            raise ValueError("Передача не найдена")

        # Recheck after locking the assignment: simultaneous retries with the same
        # key serialize here, so only the first request can insert the payment.
        existing = await session.scalar(
            select(Payment).where(Payment.operation_key == operation_key)
        )
        if existing:
            if (existing.assignment_id != assignment_id or existing.amount != amount
                    or (payment_date is not None and existing.payment_date != payment_date)
                or (notes is not None and existing.notes != notes)):
                raise ValueError("Ключ операции уже использован для другого платежа")
            return existing

        finance_result = await session.execute(
            text("""
                SELECT remaining_amount
                FROM assignment_finances
                WHERE assignment_id = :assignment_id
            """),
            {"assignment_id": assignment_id},
        )
        finance_row = finance_result.mappings().first()
        if not finance_row:
            raise ValueError("Финансовое состояние передачи не найдено")
        remaining = finance_row["remaining_amount"]
        if remaining <= 0:
            raise ValueError("Сейчас нет суммы комиссии, доступной к оплате")
        if amount > remaining:
            raise ValueError(
                f"Платёж {amount} превышает остаток комиссии {remaining}"
            )

        payment = Payment(
            assignment_id=assignment_id,
            payment_date=payment_date or date.today(),
            amount=amount,
            operation_key=operation_key,
            notes=notes.strip() if notes else None,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(
            select(Payment).where(Payment.operation_key == operation_key)
        )
        if existing and (existing.assignment_id == assignment_id and existing.amount == amount
                and (payment_date is None or existing.payment_date == payment_date)
                and (notes is None or existing.notes == notes)):
            return existing
        if existing:
            raise ValueError("Ключ операции уже использован для другого платежа") from error
        raise
    except Exception:
        await session.rollback()
        raise


async def get_refundable_payments(session: AsyncSession, assignment_id: int):
    result = await session.execute(text("""
        SELECT p.id, p.payment_date, p.amount,
               p.amount - COALESCE(SUM(r.amount), 0::NUMERIC) AS refundable_amount
        FROM payments AS p
        LEFT JOIN payment_refunds AS r ON r.payment_id = p.id
        WHERE p.assignment_id = :assignment_id
        GROUP BY p.id
        HAVING p.amount - COALESCE(SUM(r.amount), 0::NUMERIC) > 0
        ORDER BY p.payment_date, p.id
    """), {"assignment_id": assignment_id})
    return list(result.mappings().all())


async def refund_payment(session: AsyncSession, assignment_id: int, payment_id: int,
                         amount: Decimal, reason: str, author: str, operation_key: str,
                         refund_date: Optional[date] = None) -> PaymentRefund:
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
        raise ValueError("Сумма возврата должна быть конечным положительным Decimal")
    if not all(isinstance(value, str) for value in (reason, author, operation_key)):
        raise ValueError("Причина, автор и ключ должны быть текстом")
    reason = reason.strip()
    author = author.strip()
    operation_key = operation_key.strip()
    if not reason or not author or not operation_key or len(operation_key) > 128:
        raise ValueError("Укажите причину, автора и корректный ключ возврата")

    existing = await session.scalar(select(PaymentRefund).where(PaymentRefund.operation_key == operation_key))
    if existing:
        if (existing.assignment_id != assignment_id or existing.payment_id != payment_id
                or existing.amount != amount or existing.reason != reason or existing.author != author):
            raise ValueError("Ключ операции уже использован для другого возврата")
        return existing

    try:
        assignment = await session.scalar(select(Assignment).where(
            Assignment.id == assignment_id
        ).with_for_update())
        if not assignment:
            raise ValueError("Передача не найдена")
        existing = await session.scalar(select(PaymentRefund).where(PaymentRefund.operation_key == operation_key))
        if existing:
            if (existing.assignment_id != assignment_id or existing.payment_id != payment_id
                    or existing.amount != amount or existing.reason != reason or existing.author != author):
                raise ValueError("Ключ операции уже использован для другого возврата")
            return existing

        payment = await session.scalar(select(Payment).where(
            Payment.id == payment_id, Payment.assignment_id == assignment_id
        ).with_for_update())
        if not payment:
            raise ValueError("Платёж этой передачи не найден")
        finance = await session.execute(text("""
            SELECT remaining_amount FROM assignment_finances WHERE assignment_id = :assignment_id
        """), {"assignment_id": assignment_id})
        finance_row = finance.mappings().first()
        if not finance_row or finance_row["remaining_amount"] >= 0:
            raise ValueError("Переплаты для возврата нет")
        amount_due = -finance_row["remaining_amount"]
        refundable = await session.scalar(
            select(func.coalesce(func.sum(PaymentRefund.amount), 0)).where(PaymentRefund.payment_id == payment_id)
        ) or Decimal("0")
        available_from_payment = payment.amount - refundable
        if amount > amount_due or amount > available_from_payment:
            raise ValueError(
                f"Возврат превышает доступную сумму: к возврату {amount_due}, "
                f"по выбранному платежу {available_from_payment}"
            )
        refund = PaymentRefund(
            assignment_id=assignment_id,
            payment_id=payment_id,
            refund_date=refund_date or date.today(),
            amount=amount,
            reason=reason,
            author=author,
            operation_key=operation_key,
        )
        session.add(refund)
        await session.commit()
        await session.refresh(refund)
        return refund
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(select(PaymentRefund).where(PaymentRefund.operation_key == operation_key))
        if existing and (existing.assignment_id == assignment_id and existing.payment_id == payment_id
                and existing.amount == amount and existing.reason == reason and existing.author == author):
            return existing
        if existing:
            raise ValueError("Ключ операции уже использован для другого возврата") from error
        raise
    except Exception:
        await session.rollback()
        raise
