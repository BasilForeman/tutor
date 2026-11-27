from decimal import Decimal, InvalidOperation
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import text

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu
from bot.services.assignments import get_assignment_display_rows
from bot.services.finance import adjust_assignment_commission
from bot.services.payments import get_refundable_payments, refund_payment
from bot.states.finance import CommissionAdjustmentForm, RefundForm

router = Router()
CANCEL = "❌ Отмена"


def keyboard(rows):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=item)] for item in [*rows, CANCEL]],
        resize_keyboard=True,
    )


@router.message(F.text == "⚖️ Корректировка комиссии")
async def start_adjustment(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        assignments = await get_assignment_display_rows(session)
    if not assignments:
        await message.answer("Передач пока нет.", reply_markup=get_main_menu())
        return
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(CommissionAdjustmentForm.assignment)
    await message.answer("Выбери передачу для корректировки комиссии:", reply_markup=keyboard(
        [f"{item['id']} | {item['client']} — {item['tutor']} | комиссия {item['commission_amount']} ₽, остаток {item['remaining_amount']} ₽"
         for item in assignments[:50]]
    ))


@router.message(F.text == "↩️ Возврат платежа")
async def start_refund(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        rows = await get_assignment_display_rows(session, overpaid_only=True)
    if not rows:
        await message.answer("Переплаты к возврату нет.", reply_markup=get_main_menu())
        return
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(RefundForm.assignment)
    await message.answer("Выбери передачу и сумму возврата:", reply_markup=keyboard(
        [f"{row['id']} | {row['client']} — {row['tutor']} | к возврату {-row['remaining_amount']} ₽" for row in rows]
    ))


@router.message(CommissionAdjustmentForm.assignment, F.text == CANCEL)
@router.message(CommissionAdjustmentForm.amount, F.text == CANCEL)
@router.message(CommissionAdjustmentForm.reason, F.text == CANCEL)
@router.message(CommissionAdjustmentForm.confirmation, F.text == CANCEL)
@router.message(RefundForm.assignment, F.text == CANCEL)
@router.message(RefundForm.payment, F.text == CANCEL)
@router.message(RefundForm.amount, F.text == CANCEL)
@router.message(RefundForm.reason, F.text == CANCEL)
@router.message(RefundForm.confirmation, F.text == CANCEL)
async def cancel_finance_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Финансовая операция отменена.", reply_markup=get_main_menu())


@router.message(CommissionAdjustmentForm.assignment)
async def choose_adjustment_assignment(message: Message, state: FSMContext):
    try:
        assignment_id = int((message.text or "").split("|", 1)[0].strip())
    except ValueError:
        await message.answer("Выбери передачу кнопкой.")
        return
    async with async_session() as session:
        assignments = await get_assignment_display_rows(session)
        finance = next((row for row in assignments if row["id"] == assignment_id), None)
    if not finance:
        await message.answer("Финансовая карточка не найдена.")
        return
    await state.update_data(
        assignment_id=assignment_id, previous_amount=str(finance["commission_amount"]),
        assignment_label=f"Передача №{assignment_id}: {finance['client']} — {finance['tutor']}",
    )
    await state.set_state(CommissionAdjustmentForm.amount)
    await message.answer(
        f"Передача №{assignment_id}: {finance['client']} — {finance['tutor']}\n"
        f"Платных занятий: {finance['paid_lessons']}\n"
        f"Текущая комиссия: {finance['commission_amount']}; оплачено: {finance['paid_amount']}; остаток: {finance['remaining_amount']}.\n"
        "Введи новую итоговую сумму комиссии:"
    )


@router.message(CommissionAdjustmentForm.amount)
async def enter_adjustment_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечную неотрицательную сумму.")
        return
    await state.update_data(new_amount=str(amount))
    await state.set_state(CommissionAdjustmentForm.reason)
    await message.answer("Укажи причину перерасчёта:")


@router.message(CommissionAdjustmentForm.reason)
async def enter_adjustment_reason(message: Message, state: FSMContext):
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой.")
        return
    await state.update_data(reason=reason)
    data = await state.get_data()
    await state.set_state(CommissionAdjustmentForm.confirmation)
    await message.answer(
        f"Подтвердить корректировку {data['assignment_label']}?\n"
        f"Комиссия: {data['previous_amount']} → {data['new_amount']}\nПричина: {reason}\n"
        "Если комиссия станет меньше оплаченной суммы, появится отдельный возврат к оформлению.",
        reply_markup=keyboard(["✅ Подтвердить"]),
    )


@router.message(CommissionAdjustmentForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_adjustment(message: Message, state: FSMContext):
    data = await state.get_data()
    author = str(message.from_user.id) if message.from_user else "telegram"
    try:
        async with async_session() as session:
            adjustment = await adjust_assignment_commission(
                session, data["assignment_id"], Decimal(data["new_amount"]),
                data["reason"], author, data["operation_key"],
            )
    except ValueError as error:
        await message.answer(f"⚠️ {error}", reply_markup=get_main_menu())
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ Комиссия скорректирована для {data['assignment_label']}: {adjustment.previous_amount} → {adjustment.new_amount}.",
        reply_markup=get_main_menu(),
    )


@router.message(RefundForm.assignment)
async def choose_refund_assignment(message: Message, state: FSMContext):
    try:
        assignment_id = int((message.text or "").split("|", 1)[0].strip())
    except ValueError:
        await message.answer("Выбери передачу кнопкой.")
        return
    async with async_session() as session:
        rows = await get_assignment_display_rows(session, overpaid_only=True)
        assignment = next((row for row in rows if row["id"] == assignment_id), None)
        payments = await get_refundable_payments(session, assignment_id)
    if not payments:
        await message.answer("По этой передаче нет платежей, доступных для возврата.")
        return
    await state.update_data(
        assignment_id=assignment_id,
        assignment_label=(f"Передача №{assignment_id}: {assignment['client']} — {assignment['tutor']}"
                          if assignment else f"Передача №{assignment_id}"),
    )
    await state.set_state(RefundForm.payment)
    await message.answer("Выбери исходный платёж:", reply_markup=keyboard(
        [f"{item['id']} | {item['client']} — {item['tutor']} | дата {item['payment_date']} | доступно {item['refundable_amount']} ₽"
         for item in payments]
    ))


@router.message(RefundForm.payment)
async def choose_refund_payment(message: Message, state: FSMContext):
    try:
        payment_id = int((message.text or "").split("|", 1)[0].strip())
    except ValueError:
        await message.answer("Выбери платёж кнопкой.")
        return
    data = await state.get_data()
    await state.update_data(payment_id=payment_id)
    await state.set_state(RefundForm.amount)
    await message.answer("Введи сумму возврата (не больше переплаты и остатка исходного платежа):")


@router.message(RefundForm.amount)
async def enter_refund_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечную сумму больше нуля.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(RefundForm.reason)
    await message.answer("Укажи причину возврата:")


@router.message(RefundForm.reason)
async def enter_refund_reason(message: Message, state: FSMContext):
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой.")
        return
    await state.update_data(reason=reason)
    data = await state.get_data()
    await state.set_state(RefundForm.confirmation)
    await message.answer(
        f"Подтвердить возврат {data['amount']} ₽ по платежу №{data['payment_id']} "
        f"({data['assignment_label']})?\nПричина: {reason}",
        reply_markup=keyboard(["✅ Подтвердить"]),
    )


@router.message(RefundForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_refund(message: Message, state: FSMContext):
    data = await state.get_data()
    author = str(message.from_user.id) if message.from_user else "telegram"
    try:
        async with async_session() as session:
            refund = await refund_payment(
                session, data["assignment_id"], data["payment_id"], Decimal(data["amount"]),
                data["reason"], author, data["operation_key"],
            )
    except ValueError as error:
        await message.answer(f"⚠️ {error}", reply_markup=get_main_menu())
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ Возврат №{refund.id} на сумму {refund.amount} ₽ по {data['assignment_label']} сохранён.",
        reply_markup=get_main_menu(),
    )
