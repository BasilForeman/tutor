from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Assignment, Payment


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
            if existing.assignment_id != assignment_id or existing.amount != amount:
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
    except Exception:
        await session.rollback()
        raise
