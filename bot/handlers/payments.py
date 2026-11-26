from decimal import Decimal, InvalidOperation
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import text

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu
from bot.services.assignments import get_assignments
from bot.services.payments import create_payment
from bot.states.payments import PaymentForm

router = Router()
CANCEL = "❌ Отмена"
SKIP = "⏭ Пропустить"


def keyboard(rows):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=value)] for value in rows],
        resize_keyboard=True,
    )


@router.message(F.text == "💰 Финансы")
async def show_finances(message: Message):
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT a.id, a.tutor_id, a.client_id, a.payment_due_date,
                   f.commission_amount, f.paid_amount, f.remaining_amount
            FROM assignment_finances AS f
            JOIN assignments AS a ON a.id = f.assignment_id
            WHERE f.remaining_amount <> 0
            ORDER BY a.payment_due_date NULLS LAST, a.id
        """))
        rows = result.mappings().all()
    if not rows:
        await message.answer("Незакрытых комиссий нет.", reply_markup=get_main_menu())
        return
    total = sum((max(row["remaining_amount"], Decimal("0")) for row in rows), Decimal("0"))
    refund_total = sum((max(-row["remaining_amount"], Decimal("0")) for row in rows), Decimal("0"))
    lines = [f"<b>Долг по комиссиям: {total}; переплата к возврату: {refund_total}</b>"]
    for row in rows[:30]:
        due = row["payment_due_date"].isoformat() if row["payment_due_date"] else "срок не задан"
        label = (
            f"долг {row['remaining_amount']}" if row["remaining_amount"] > 0
            else f"к возврату {-row['remaining_amount']}"
        )
        lines.append(
            f"Передача №{row['id']} | ученик №{row['client_id']} | "
            f"репетитор №{row['tutor_id']} | {label} | {due}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_menu())


@router.message(F.text == "💵 Записать платёж")
async def start_payment(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        assignments = await get_assignments(session)
    if not assignments:
        await message.answer("Сначала создай передачу.", reply_markup=get_main_menu())
        return
    rows = [
        f"{item.id} | ученик {item.client_id}, репетитор {item.tutor_id}, комиссия {item.commission_amount}"
        for item in assignments
    ]
    rows.append(CANCEL)
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(PaymentForm.assignment)
    await message.answer("Выбери передачу для платежа:", reply_markup=keyboard(rows))


@router.message(PaymentForm.assignment, F.text == CANCEL)
@router.message(PaymentForm.amount, F.text == CANCEL)
@router.message(PaymentForm.notes, F.text == CANCEL)
@router.message(PaymentForm.confirmation, F.text == CANCEL)
async def cancel_payment(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Запись платежа отменена.", reply_markup=get_main_menu())


@router.message(PaymentForm.assignment)
async def choose_assignment(message: Message, state: FSMContext):
    try:
        assignment_id = int((message.text or "").split("|", 1)[0].strip())
    except ValueError:
        await message.answer("Выбери передачу кнопкой из списка.")
        return
    async with async_session() as session:
        assignments = await get_assignments(session)
    assignment = next((item for item in assignments if item.id == assignment_id), None)
    if not assignment:
        await message.answer("Передача не найдена. Выбери из списка.")
        return
    await state.update_data(
        assignment_id=assignment.id,
        commission_amount=str(assignment.commission_amount),
    )
    await state.set_state(PaymentForm.amount)
    await message.answer("Введи сумму частичного или полного платежа:", reply_markup=keyboard([CANCEL]))


@router.message(PaymentForm.amount)
async def enter_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Нужна конечная сумма больше нуля.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(PaymentForm.notes)
    await message.answer("Комментарий к платежу или пропусти:", reply_markup=keyboard([SKIP, CANCEL]))


@router.message(PaymentForm.notes, F.text == SKIP)
@router.message(PaymentForm.notes)
async def enter_notes(message: Message, state: FSMContext):
    notes = None if message.text == SKIP else (message.text or "").strip() or None
    await state.update_data(notes=notes)
    data = await state.get_data()
    await state.set_state(PaymentForm.confirmation)
    await message.answer(
        f"Подтвердить платёж {data['amount']} по передаче №{data['assignment_id']}?",
        reply_markup=keyboard(["✅ Подтвердить", CANCEL]),
    )


@router.message(PaymentForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session() as session:
            payment = await create_payment(
                session=session,
                assignment_id=data["assignment_id"],
                amount=Decimal(data["amount"]),
                operation_key=data["operation_key"],
                notes=data.get("notes"),
            )
    except ValueError as error:
        await state.clear()
        await message.answer(f"⚠️ {error}", reply_markup=get_main_menu())
        return
    await state.clear()
    await message.answer(
        f"✅ Платёж №{payment.id} на сумму {payment.amount} записан.",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "⬅️ Главное меню")
async def payment_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())
