from decimal import Decimal, InvalidOperation
from uuid import uuid4
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import text

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu, get_payouts_menu
from bot.services.tutor_payments import (
    create_tutor_payment_batch,
    get_tutor_outstanding_assignments,
    get_tutor_payment_history,
    get_tutors_with_debt,
    parse_allocation_lines,
)
from bot.states.payments import PaymentForm

router = Router()
CANCEL = "❌ Отмена"
SKIP = "⏭ Пропустить"


def keyboard(rows):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=value)] for value in rows],
        resize_keyboard=True,
    )


@router.message(F.text == "💰 Выплаты")
async def open_payouts_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Платежи и комиссии:", reply_markup=get_payouts_menu())


@router.message(F.text == "📋 Текущие долги")
async def show_finances(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT a.id, a.tutor_id, t.nickname AS tutor, a.client_id,
                   f.commission_amount, f.paid_amount, f.remaining_amount
            FROM assignment_finances AS f
            JOIN assignments AS a ON a.id = f.assignment_id
            JOIN tutors AS t ON t.id = a.tutor_id
            WHERE f.remaining_amount <> 0
            ORDER BY t.nickname, a.id
        """))
        rows = result.mappings().all()
    if not rows:
        await message.answer("Незакрытых комиссий нет.", reply_markup=get_payouts_menu())
        return
    total = sum((max(row["remaining_amount"], Decimal("0")) for row in rows), Decimal("0"))
    refund_total = sum((max(-row["remaining_amount"], Decimal("0")) for row in rows), Decimal("0"))
    lines = [f"<b>Долг по комиссиям: {total}; переплата к возврату: {refund_total}</b>"]
    for row in rows[:40]:
        balance = row["remaining_amount"]
        label = f"долг {balance}" if balance > 0 else f"к возврату {-balance}"
        lines.append(f"Передача №{row['id']} | {escape(row['tutor'])} | ученик №{row['client_id']} | {label}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_payouts_menu())


@router.message(F.text == "💵 Записать платёж")
async def start_payment(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        tutors = await get_tutors_with_debt(session)
    if not tutors:
        await message.answer("Сейчас нет задолженности по комиссиям.", reply_markup=get_payouts_menu())
        return
    options = [f"{item['id']} | {item['nickname']} | долг {item['debt']}" for item in tutors]
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(PaymentForm.tutor)
    await message.answer("Выбери репетитора, от которого получен платёж:", reply_markup=keyboard(options + [CANCEL]))


@router.message(F.text == "🧾 История платежей")
async def start_payment_history(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        result = await session.execute(text("SELECT id, nickname FROM tutors ORDER BY lower(nickname), id"))
        tutors = result.mappings().all()
    if not tutors:
        await message.answer("Репетиторов пока нет.", reply_markup=get_payouts_menu())
        return
    await state.set_state(PaymentForm.history_tutor)
    await message.answer(
        "Выбери репетитора для просмотра платежей:",
        reply_markup=keyboard([f"{item['id']} | {item['nickname']}" for item in tutors] + [CANCEL]),
    )


@router.message(PaymentForm.tutor, F.text == CANCEL)
@router.message(PaymentForm.amount, F.text == CANCEL)
@router.message(PaymentForm.allocations, F.text == CANCEL)
@router.message(PaymentForm.notes, F.text == CANCEL)
@router.message(PaymentForm.confirmation, F.text == CANCEL)
@router.message(PaymentForm.history_tutor, F.text == CANCEL)
async def cancel_payment(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_payouts_menu())


def selected_id(value: str | None) -> int:
    try:
        return int((value or "").split("|", 1)[0].strip())
    except ValueError:
        raise ValueError("Выбери запись кнопкой из списка.") from None


@router.message(PaymentForm.tutor)
async def choose_payment_tutor(message: Message, state: FSMContext):
    try:
        tutor_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    async with async_session() as session:
        tutors = await get_tutors_with_debt(session)
        tutor = next((item for item in tutors if item["id"] == tutor_id), None)
        assignments = await get_tutor_outstanding_assignments(session, tutor_id) if tutor else []
    if not tutor or not assignments:
        await message.answer("У этого репетитора нет непогашенной задолженности. Выбери из списка.")
        return
    await state.update_data(tutor_id=tutor_id, tutor_name=tutor["nickname"])
    await state.set_state(PaymentForm.amount)
    await message.answer(
        f"Получен платёж от {tutor['nickname']}. Введи фактически полученную сумму:",
        reply_markup=keyboard([CANCEL]),
    )


@router.message(PaymentForm.amount)
async def enter_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Нужна конечная сумма больше нуля.")
        return
    data = await state.get_data()
    async with async_session() as session:
        assignments = await get_tutor_outstanding_assignments(session, data["tutor_id"])
    available = sum((row["remaining_amount"] for row in assignments), Decimal("0"))
    if amount > available:
        await message.answer(
            f"Сумма больше общей задолженности репетитора ({available} ₽). "
            "Введи фактически полученную сумму в пределах доступного долга или отмени."
        )
        return
    await state.update_data(amount=str(amount))
    await state.set_state(PaymentForm.allocations)
    lines = [f"Долги {data['tutor_name']} по передачам:"]
    lines.extend(f"№{row['assignment_id']} — {row['client']} — остаток {row['remaining_amount']} ₽" for row in assignments)
    lines.append(f"\nРаспредели {amount} ₽ по строкам вида ID=сумма, по одной на строку.")
    lines.append("Сумма распределений должна совпасть с платежом; превышать долг передачи нельзя.")
    await message.answer("\n".join(lines), reply_markup=keyboard([CANCEL]))


@router.message(PaymentForm.allocations)
async def enter_allocations(message: Message, state: FSMContext):
    try:
        allocations = parse_allocation_lines(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    data = await state.get_data()
    if sum((amount for _, amount in allocations), Decimal("0")) != Decimal(data["amount"]):
        await message.answer(f"Сумма распределений должна равняться {data['amount']} ₽. Исправь строки.")
        return
    await state.update_data(allocations=[(assignment_id, str(amount)) for assignment_id, amount in allocations])
    await state.set_state(PaymentForm.notes)
    await message.answer("Комментарий к общему платежу или пропусти:", reply_markup=keyboard([SKIP, CANCEL]))


@router.message(PaymentForm.notes, F.text == SKIP)
@router.message(PaymentForm.notes)
async def enter_notes(message: Message, state: FSMContext):
    notes = None if message.text == SKIP else (message.text or "").strip() or None
    await state.update_data(notes=notes)
    data = await state.get_data()
    parts = "\n".join(f"• Передача №{assignment_id}: {amount} ₽" for assignment_id, amount in data["allocations"])
    await state.set_state(PaymentForm.confirmation)
    await message.answer(
        f"Получено от {data['tutor_name']}: {data['amount']} ₽\n{parts}\n\nПодтвердить один платёж с этим распределением?",
        reply_markup=keyboard(["✅ Подтвердить", CANCEL]),
    )


@router.message(PaymentForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session() as session:
            batch, allocations = await create_tutor_payment_batch(
                session=session,
                tutor_id=data["tutor_id"],
                amount=Decimal(data["amount"]),
                allocations=[(assignment_id, Decimal(amount)) for assignment_id, amount in data["allocations"]],
                operation_key=data["operation_key"],
                notes=data.get("notes"),
            )
    except ValueError as error:
        # Keep the form open so Sonia can correct a stale debt allocation.
        await state.set_state(PaymentForm.allocations)
        await message.answer(f"⚠️ {error}\nВведи распределение заново или отмени.", reply_markup=keyboard([CANCEL]))
        return
    await state.clear()
    allocated = "\n".join(f"• Передача №{payment.assignment_id}: {payment.amount} ₽" for payment in allocations)
    await message.answer(
        f"✅ Платёж №{batch.id} на {batch.amount} ₽ записан.\nРаспределение:\n{allocated}",
        reply_markup=get_payouts_menu(),
    )


@router.message(PaymentForm.history_tutor)
async def show_payment_history(message: Message, state: FSMContext):
    try:
        tutor_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    async with async_session() as session:
        history = await get_tutor_payment_history(session, tutor_id)
        tutor = await session.execute(text("SELECT nickname FROM tutors WHERE id=:id"), {"id": tutor_id})
        tutor_name = tutor.scalar_one_or_none()
    await state.clear()
    if not tutor_name:
        await message.answer("Репетитор не найден.", reply_markup=get_payouts_menu())
        return
    if not history:
        await message.answer(f"У {tutor_name} пока нет записанных платежей.", reply_markup=get_payouts_menu())
        return
    lines = [f"<b>Платежи: {escape(tutor_name)}</b>"]
    for item in history:
        batch = item["batch"]
        lines.append(f"\nПлатёж №{batch['id']} от {batch['payment_date']}: {batch['amount']} ₽")
        for part in item["allocations"]:
            refunded = part["refunded"]
            lines.append(f"  ↳ Передача №{part['assignment_id']} ({escape(part['client'])}): {part['amount']} ₽; возврат {refunded} ₽")
        if batch["notes"]:
            lines.append(f"  Комментарий: {escape(batch['notes'])}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_payouts_menu())


@router.message(F.text == "⬅️ Главное меню")
async def payment_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())
