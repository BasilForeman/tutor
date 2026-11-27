from decimal import Decimal, InvalidOperation
from html import escape
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import text

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu, get_payouts_menu
from bot.presentation import commission_mode_label, format_amount, person_label
from bot.services.assignments import get_assignment_display_rows
from bot.services.tutor_payments import (
    allocate_tutor_advance,
    create_tutor_payment_batch,
    get_tutor_advances,
    get_tutor_outstanding_assignments,
    get_tutor_payment_history,
    get_tutors_for_payments,
)
from bot.states.payments import PaymentForm

router = Router()
CANCEL = "❌ Отмена"
SKIP = "⏭ Пропустить"
FINISH = "✅ Завершить распределение"
BACK_TO_ALLOCATIONS = "↩️ Вернуться к распределению"


def keyboard(rows):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=value)] for value in rows],
        resize_keyboard=True,
    )


def selected_id(value: str | None) -> int:
    try:
        return int((value or "").split("|", 1)[0].strip())
    except ValueError:
        raise ValueError("Выбери запись кнопкой из списка.") from None


def _allocation_total(allocations) -> Decimal:
    return sum((Decimal(item["amount"]) for item in allocations), Decimal("0"))


def _transfer_label(row) -> str:
    if row.get("label"):
        return row["label"]
    student = person_label(row["client"], row.get("client_contact"))
    return f"Передача №{row['assignment_id']} — {student} — {row['tutor']}"


def _allocation_summary(allocations) -> str:
    if not allocations:
        return "Распределений пока нет."
    return "\n".join(
        f"• {_transfer_label(item)}: {format_amount(item['amount'])} ₽"
        for item in allocations
    )


def _remaining_assignment_debt(row, allocations) -> Decimal:
    already = sum((Decimal(item["amount"]) for item in allocations
                   if item["assignment_id"] == row["assignment_id"]), Decimal("0"))
    return max(Decimal(row["remaining_amount"]) - already, Decimal("0"))


async def _show_allocation_options(message: Message, state: FSMContext, *, advance: bool = False):
    data = await state.get_data()
    async with async_session() as session:
        assignments = await get_tutor_outstanding_assignments(session, data["tutor_id"])
    allocations = data.get("allocations", [])
    options = []
    visible = []
    for row in assignments:
        remaining = _remaining_assignment_debt(row, allocations)
        if remaining <= 0:
            continue
        label = (
            f"{row['assignment_id']} | {person_label(row['client'], row.get('client_contact'))} — "
            f"{row['tutor']} | долг {format_amount(remaining)} ₽ | занятий {row['paid_lessons']}"
        )
        options.append(label)
        visible.append((row, remaining))
    options.extend([FINISH, CANCEL])
    remaining_payment = (Decimal(data["amount"]) - _allocation_total(allocations)
                         if not advance else Decimal(data["available_advance"]) - _allocation_total(allocations))
    heading = (
        f"Доступный аванс: {format_amount(data['available_advance'])} ₽\n"
        if advance else f"Получено: {format_amount(data['amount'])} ₽\n"
    )
    text_lines = [heading + f"Ещё не распределено: {format_amount(remaining_payment)} ₽"]
    for row, remaining in visible:
        text_lines.append(
            f"\n№{row['assignment_id']} — {person_label(row['client'], row.get('client_contact'))} — "
            f"{row['tutor']}\nНачислено {format_amount(row['commission_amount'])} ₽; "
            f"оплачено {format_amount(row['paid_amount'])} ₽; остаток {format_amount(remaining)} ₽; "
            f"платных занятий {row['paid_lessons']}"
        )
    text_lines.append("\nВыбери передачу для доли платежа или заверши распределение.")
    await message.answer("".join(text_lines), reply_markup=keyboard(options))


async def _begin_new_payment_allocations(message: Message, state: FSMContext, *, allow_advance: bool):
    await state.update_data(allocations=[], allow_advance=allow_advance)
    await state.set_state(PaymentForm.allocation_select)
    await _show_allocation_options(message, state)


async def _begin_notes(message: Message, state: FSMContext):
    data = await state.get_data()
    allocated = _allocation_total(data.get("allocations", []))
    advance = Decimal(data["amount"]) - allocated
    if advance < 0:
        await message.answer("Распределения больше полученной суммы. Исправь распределение.")
        await state.set_state(PaymentForm.allocation_select)
        await _show_allocation_options(message, state)
        return
    if advance > 0 and not data.get("allow_advance"):
        await state.update_data(unallocated_advance=str(advance))
        await state.set_state(PaymentForm.advance_remainder_confirmation)
        await message.answer(
            f"Остаток {format_amount(advance)} ₽ не распределён. Сохранить его как аванс "
            "репетитора? Он не будет увеличивать комиссию.",
            reply_markup=keyboard(["✅ Сохранить как аванс", BACK_TO_ALLOCATIONS, CANCEL]),
        )
        return
    await state.update_data(unallocated_advance=str(advance))
    await state.set_state(PaymentForm.notes)
    message_text = "Комментарий к полученному платежу или пропусти:"
    if advance:
        message_text = f"Аванс к зачислению: {format_amount(advance)} ₽. " + message_text
    await message.answer(message_text, reply_markup=keyboard([SKIP, CANCEL]))


@router.message(F.text == "💰 Выплаты")
async def open_payouts_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Платежи и комиссии:", reply_markup=get_payouts_menu())


@router.message(F.text == "📋 Долги и начисления")
async def show_finances(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        rows = await get_assignment_display_rows(session)
        tutors = await get_tutors_for_payments(session)
    if not rows:
        await message.answer("Передач пока нет.", reply_markup=get_payouts_menu())
        return
    total_debt = sum((max(Decimal(row["remaining_amount"]), Decimal("0")) for row in rows), Decimal("0"))
    total_overpaid = sum((max(-Decimal(row["remaining_amount"]), Decimal("0")) for row in rows), Decimal("0"))
    total_advance = sum((Decimal(row["advance"]) for row in tutors), Decimal("0"))
    lines = [
        f"<b>Долг по комиссиям: {format_amount(total_debt)} ₽</b>",
        f"Авансы репетиторов: {format_amount(total_advance)} ₽ | переплаты по передачам: {format_amount(total_overpaid)} ₽",
    ]
    for row in rows:
        balance = Decimal(row["remaining_amount"])
        status = f"долг {format_amount(balance)} ₽" if balance > 0 else f"переплата {format_amount(-balance)} ₽" if balance < 0 else "расчёт закрыт"
        student = escape(person_label(row["client"], row.get("client_contact")))
        tutor = escape(row["tutor"])
        mode = escape(commission_mode_label(row))
        lines.append(
            f"\n<b>Передача №{row['id']}</b> | ученик {student} | репетитор {tutor}\n"
            f"Условия: {mode} | платных занятий: {row['paid_lessons']}\n"
            f"Начислено: {format_amount(row['commission_amount'])} ₽ | "
            f"оплачено: {format_amount(row['paid_amount'])} ₽ | {status}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_payouts_menu())


@router.message(F.text == "💵 Записать платёж")
async def start_payment(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        tutors = await get_tutors_for_payments(session)
    if not tutors:
        await message.answer("Активных репетиторов пока нет.", reply_markup=get_payouts_menu())
        return
    options = [
        f"{item['id']} | {item['nickname']}{' (архив)' if not item['is_active'] else ''} | долг {format_amount(item['debt'])} ₽ | аванс {format_amount(item['advance'])} ₽"
        for item in tutors
    ]
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(PaymentForm.tutor)
    await message.answer("Выбери репетитора, от которого фактически получен платёж:", reply_markup=keyboard(options + [CANCEL]))


@router.message(F.text == "🪙 Распределить аванс")
async def start_advance_distribution(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(operation_key=uuid4().hex)
    async with async_session() as session:
        tutors = [row for row in await get_tutors_for_payments(session) if Decimal(row["advance"]) > 0]
    if not tutors:
        await message.answer("Нераспределённых авансов нет.", reply_markup=get_payouts_menu())
        return
    await state.set_state(PaymentForm.advance_tutor)
    await message.answer(
        "Выбери репетитора, чей аванс нужно распределить:",
        reply_markup=keyboard([f"{r['id']} | {r['nickname']}{' (архив)' if not r['is_active'] else ''} | аванс {format_amount(r['advance'])} ₽" for r in tutors] + [CANCEL]),
    )


@router.message(F.text == "🧾 История платежей")
async def start_payment_history(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        result = await session.execute(text("SELECT id,nickname FROM tutors ORDER BY lower(nickname),id"))
        tutors = result.mappings().all()
    if not tutors:
        await message.answer("Репетиторов пока нет.", reply_markup=get_payouts_menu())
        return
    await state.set_state(PaymentForm.history_tutor)
    await message.answer("Выбери репетитора для просмотра платежей:", reply_markup=keyboard([f"{r['id']} | {r['nickname']}" for r in tutors] + [CANCEL]))


@router.message(PaymentForm.tutor, F.text == CANCEL)
@router.message(PaymentForm.amount, F.text == CANCEL)
@router.message(PaymentForm.overpayment_confirmation, F.text == CANCEL)
@router.message(PaymentForm.allocation_select, F.text == CANCEL)
@router.message(PaymentForm.allocation_amount, F.text == CANCEL)
@router.message(PaymentForm.advance_remainder_confirmation, F.text == CANCEL)
@router.message(PaymentForm.notes, F.text == CANCEL)
@router.message(PaymentForm.confirmation, F.text == CANCEL)
@router.message(PaymentForm.history_tutor, F.text == CANCEL)
@router.message(PaymentForm.advance_tutor, F.text == CANCEL)
@router.message(PaymentForm.advance_batch, F.text == CANCEL)
@router.message(PaymentForm.advance_select, F.text == CANCEL)
@router.message(PaymentForm.advance_amount, F.text == CANCEL)
@router.message(PaymentForm.advance_confirmation, F.text == CANCEL)
async def cancel_payment(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_payouts_menu())


@router.message(PaymentForm.tutor)
async def choose_payment_tutor(message: Message, state: FSMContext):
    try:
        tutor_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    async with async_session() as session:
        tutors = await get_tutors_for_payments(session)
        tutor = next((row for row in tutors if row["id"] == tutor_id), None)
    if not tutor:
        await message.answer("Репетитор не найден. Выбери его кнопкой.")
        return
    await state.update_data(tutor_id=tutor_id, tutor_name=tutor["nickname"])
    await state.set_state(PaymentForm.amount)
    await message.answer("Введи фактически полученную сумму:", reply_markup=keyboard([CANCEL]))


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
    total_debt = sum((Decimal(row["remaining_amount"]) for row in assignments), Decimal("0"))
    await state.update_data(amount=str(amount), outstanding_total=str(total_debt))
    if amount > total_debt:
        excess = amount - total_debt
        await state.set_state(PaymentForm.overpayment_confirmation)
        await message.answer(
            f"⚠️ Получено: {format_amount(amount)} ₽. Текущий долг {data['tutor_name']}: "
            f"{format_amount(total_debt)} ₽. Превышение: {format_amount(excess)} ₽.\n"
            "Превышение не будет начислено как комиссия или распределено автоматически. "
            "Если продолжить, нераспределённый остаток будет сохранён как аванс.",
            reply_markup=keyboard(["✅ Продолжить с авансом", CANCEL]),
        )
        return
    await _begin_new_payment_allocations(message, state, allow_advance=False)


@router.message(PaymentForm.overpayment_confirmation, F.text == "✅ Продолжить с авансом")
async def confirm_overpayment_handling(message: Message, state: FSMContext):
    await _begin_new_payment_allocations(message, state, allow_advance=True)


@router.message(PaymentForm.allocation_select, F.text == FINISH)
async def finish_new_payment_allocations(message: Message, state: FSMContext):
    await _begin_notes(message, state)


@router.message(PaymentForm.allocation_select)
async def choose_new_payment_assignment(message: Message, state: FSMContext):
    try:
        assignment_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    data = await state.get_data()
    async with async_session() as session:
        rows = await get_tutor_outstanding_assignments(session, data["tutor_id"])
    row = next((item for item in rows if item["assignment_id"] == assignment_id), None)
    if not row:
        await message.answer("Передача не найдена или задолженность уже погашена. Обновляю список.")
        await _show_allocation_options(message, state)
        return
    remaining = _remaining_assignment_debt(row, data.get("allocations", []))
    unallocated = Decimal(data["amount"]) - _allocation_total(data.get("allocations", []))
    if remaining <= 0 or unallocated <= 0:
        await message.answer("Эту передачу нельзя выбрать на текущем остатке. Выбери другую.")
        return
    label = _transfer_label(row)
    await state.update_data(selected_assignment_id=assignment_id, selected_assignment_label=label,
                            selected_assignment_debt=str(remaining))
    await state.set_state(PaymentForm.allocation_amount)
    await message.answer(
        f"{label}\nТекущий остаток: {format_amount(remaining)} ₽. "
        f"Не распределено по платежу: {format_amount(unallocated)} ₽.\n"
        "Введи сумму для этой передачи:", reply_markup=keyboard([CANCEL]),
    )


@router.message(PaymentForm.allocation_amount)
async def enter_new_payment_allocation(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечную сумму больше нуля.")
        return
    data = await state.get_data()
    pending = data.get("allocations", [])
    debt = Decimal(data["selected_assignment_debt"])
    unallocated = Decimal(data["amount"]) - _allocation_total(pending)
    if amount > debt or amount > unallocated:
        await message.answer(
            f"Сумма не должна превышать долг по передаче ({format_amount(debt)} ₽) "
            f"или остаток платежа ({format_amount(unallocated)} ₽)."
        )
        return
    pending.append({"assignment_id": data["selected_assignment_id"], "amount": str(amount),
                    "label": data["selected_assignment_label"]})
    await state.update_data(allocations=pending)
    await state.set_state(PaymentForm.allocation_select)
    await message.answer(
        f"Добавлено {format_amount(amount)} ₽: {data['selected_assignment_label']}\n"
        f"Осталось распределить: {format_amount(Decimal(data['amount']) - _allocation_total(pending))} ₽\n"
        f"Уже распределено: {_allocation_summary(pending)}"
    )
    await _show_allocation_options(message, state)


@router.message(PaymentForm.advance_remainder_confirmation, F.text == BACK_TO_ALLOCATIONS)
async def continue_payment_allocation(message: Message, state: FSMContext):
    await state.set_state(PaymentForm.allocation_select)
    await _show_allocation_options(message, state)


@router.message(PaymentForm.advance_remainder_confirmation, F.text == "✅ Сохранить как аванс")
async def confirm_remainder_as_advance(message: Message, state: FSMContext):
    await state.update_data(allow_advance=True)
    await state.set_state(PaymentForm.notes)
    data = await state.get_data()
    await message.answer(
        f"Аванс {format_amount(data['unallocated_advance'])} ₽ подтверждён. "
        "Комментарий к платежу или пропусти:", reply_markup=keyboard([SKIP, CANCEL]),
    )


@router.message(PaymentForm.notes, F.text == SKIP)
@router.message(PaymentForm.notes)
async def enter_notes(message: Message, state: FSMContext):
    notes = None if message.text == SKIP else (message.text or "").strip() or None
    await state.update_data(notes=notes)
    data = await state.get_data()
    await state.set_state(PaymentForm.confirmation)
    advance = Decimal(data["unallocated_advance"])
    await message.answer(
        f"Получено от {data['tutor_name']}: {format_amount(data['amount'])} ₽\n"
        f"Распределения:\n{_allocation_summary(data['allocations'])}\n"
        f"Аванс без комиссии: {format_amount(advance)} ₽\n\nПодтвердить запись?",
        reply_markup=keyboard(["✅ Подтвердить", CANCEL]),
    )


@router.message(PaymentForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session() as session:
            batch, allocations = await create_tutor_payment_batch(
                session=session, tutor_id=data["tutor_id"], amount=Decimal(data["amount"]),
                allocations=[(item["assignment_id"], Decimal(item["amount"])) for item in data["allocations"]],
                operation_key=data["operation_key"], notes=data.get("notes"),
                allow_advance=bool(data.get("allow_advance")),
            )
    except ValueError as error:
        await message.answer(f"⚠️ {error}\nПлатёж не записан. Начни операцию заново.", reply_markup=get_payouts_menu())
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ Получение №{batch.id}: {format_amount(batch.amount)} ₽ от {data['tutor_name']} записано.\n"
        f"Распределено: {_allocation_summary(data['allocations'])}\n"
        f"Остаток авансом: {format_amount(batch.amount - sum((p.amount for p in allocations), Decimal('0')))} ₽",
        reply_markup=get_payouts_menu(),
    )


@router.message(PaymentForm.advance_tutor)
async def choose_advance_tutor(message: Message, state: FSMContext):
    try:
        tutor_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    async with async_session() as session:
        tutors = await get_tutors_for_payments(session)
        tutor = next((row for row in tutors if row["id"] == tutor_id and Decimal(row["advance"]) > 0), None)
        advances = await get_tutor_advances(session, tutor_id) if tutor else []
    if not tutor or not advances:
        await message.answer("Доступный аванс не найден. Обнови список.")
        return
    await state.update_data(tutor_id=tutor_id, tutor_name=tutor["nickname"])
    await state.set_state(PaymentForm.advance_batch)
    await message.answer(
        "Выбери получение, из которого распределить аванс:",
        reply_markup=keyboard([f"{r['batch_id']} | {r['payment_date']} | получено {format_amount(r['received'])} ₽ | доступно {format_amount(r['available'])} ₽" for r in advances] + [CANCEL]),
    )


@router.message(PaymentForm.advance_batch)
async def choose_advance_batch(message: Message, state: FSMContext):
    try:
        batch_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    data = await state.get_data()
    async with async_session() as session:
        advances = await get_tutor_advances(session, data["tutor_id"])
        batch = next((row for row in advances if row["batch_id"] == batch_id), None)
        assignments = await get_tutor_outstanding_assignments(session, data["tutor_id"]) if batch else []
    if not batch:
        await message.answer("У этого получения больше нет свободного аванса.")
        return
    await state.update_data(advance_batch_id=batch_id, available_advance=str(batch["available"]),
                           advance_received_date=str(batch["payment_date"]), allocations=[])
    await state.set_state(PaymentForm.advance_select)
    if not assignments:
        await message.answer("У этого репетитора сейчас нет долга по передачам, на который можно распределить аванс.", reply_markup=get_payouts_menu())
        await state.clear()
        return
    options = [f"{r['assignment_id']} | {person_label(r['client'], r.get('client_contact'))} — {r['tutor']} | долг {format_amount(r['remaining_amount'])} ₽" for r in assignments]
    await message.answer(
        f"Аванс от {batch['payment_date']}: доступно {format_amount(batch['available'])} ₽.\nВыбери передачу для распределения:",
        reply_markup=keyboard(options + [FINISH, CANCEL]),
    )


@router.message(PaymentForm.advance_select, F.text == FINISH)
async def finish_advance_allocations(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("allocations"):
        await message.answer("Добавь хотя бы одно распределение аванса.")
        return
    total = _allocation_total(data["allocations"])
    await state.update_data(advance_allocated=str(total), advance_remaining=str(Decimal(data["available_advance"]) - total))
    await state.set_state(PaymentForm.advance_confirmation)
    await message.answer(
        f"Аванс от {data['advance_received_date']}: распределить {format_amount(total)} ₽\n"
        f"{_allocation_summary(data['allocations'])}\n"
        f"Останется авансом: {format_amount(Decimal(data['available_advance']) - total)} ₽\n\nПодтвердить?",
        reply_markup=keyboard(["✅ Подтвердить", BACK_TO_ALLOCATIONS, CANCEL]),
    )


@router.message(PaymentForm.advance_select)
async def choose_advance_assignment(message: Message, state: FSMContext):
    try:
        assignment_id = selected_id(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    data = await state.get_data()
    async with async_session() as session:
        assignments = await get_tutor_outstanding_assignments(session, data["tutor_id"])
    row = next((r for r in assignments if r["assignment_id"] == assignment_id), None)
    already = sum((Decimal(item["amount"]) for item in data.get("allocations", [])
                   if item["assignment_id"] == assignment_id), Decimal("0"))
    if not row or Decimal(row["remaining_amount"]) <= already:
        await message.answer("Передача не найдена или её долг уже распределён. Выбери другую.")
        return
    available = Decimal(data["available_advance"]) - _allocation_total(data.get("allocations", []))
    debt = Decimal(row["remaining_amount"]) - already
    label = _transfer_label(row)
    await state.update_data(selected_assignment_id=assignment_id, selected_assignment_label=label,
                           selected_assignment_debt=str(debt), selected_advance_available=str(available))
    await state.set_state(PaymentForm.advance_amount)
    await message.answer(
        f"{label}\nДолг: {format_amount(debt)} ₽; доступный аванс: {format_amount(available)} ₽.\n"
        "Сколько распределить?",
        reply_markup=keyboard([CANCEL]),
    )


@router.message(PaymentForm.advance_amount)
async def enter_advance_allocation(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечную сумму больше нуля.")
        return
    data = await state.get_data()
    debt = Decimal(data["selected_assignment_debt"])
    available = Decimal(data["selected_advance_available"])
    if amount > debt or amount > available:
        await message.answer(
            f"Сумма не должна превышать долг ({format_amount(debt)} ₽) "
            f"или свободный аванс ({format_amount(available)} ₽)."
        )
        return
    allocations = data.get("allocations", [])
    allocations.append({"assignment_id": data["selected_assignment_id"], "amount": str(amount),
                        "label": data["selected_assignment_label"]})
    await state.update_data(allocations=allocations)
    await state.set_state(PaymentForm.advance_select)
    await message.answer(f"Добавлено {format_amount(amount)} ₽: {data['selected_assignment_label']}\n{_allocation_summary(allocations)}")
    async with async_session() as session:
        assignments = await get_tutor_outstanding_assignments(session, data["tutor_id"])
    remaining = []
    for row in assignments:
        balance = _remaining_assignment_debt(row, allocations)
        if balance > 0:
            remaining.append(f"{row['assignment_id']} | {person_label(row['client'], row.get('client_contact'))} — {row['tutor']} | долг {format_amount(balance)} ₽")
    await message.answer(
        f"Ещё не распределено: {format_amount(Decimal(data['available_advance']) - _allocation_total(allocations))} ₽. Выбери следующую передачу или заверши.",
        reply_markup=keyboard(remaining + [FINISH, CANCEL]),
    )


@router.message(PaymentForm.advance_confirmation, F.text == BACK_TO_ALLOCATIONS)
async def edit_advance_allocations(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(PaymentForm.advance_select)
    async with async_session() as session:
        assignments = await get_tutor_outstanding_assignments(session, data["tutor_id"])
    options = [f"{r['assignment_id']} | {person_label(r['client'], r.get('client_contact'))} — {r['tutor']} | долг {format_amount(_remaining_assignment_debt(r, data['allocations']))} ₽"
               for r in assignments if _remaining_assignment_debt(r, data['allocations']) > 0]
    await message.answer("Продолжи распределение:", reply_markup=keyboard(options + [FINISH, CANCEL]))


@router.message(PaymentForm.advance_confirmation, F.text == "✅ Подтвердить")
async def confirm_advance_allocation(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session() as session:
            allocations = await allocate_tutor_advance(
                session, tutor_id=data["tutor_id"], batch_id=data["advance_batch_id"],
                allocations=[(item["assignment_id"], Decimal(item["amount"])) for item in data["allocations"]],
                operation_key=data["operation_key"],
            )
    except ValueError as error:
        await state.clear()
        await message.answer(f"⚠️ {error}\nАванс не изменён. Начни распределение заново.", reply_markup=get_payouts_menu())
        return
    await state.clear()
    await message.answer(
        f"✅ Из ранее полученного аванса распределено {format_amount(sum((p.amount for p in allocations), Decimal('0')))} ₽.\n"
        f"{_allocation_summary(data['allocations'])}",
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
        lines.append(
            f"\nПолучение №{batch['id']} от {batch['payment_date']}: "
            f"{format_amount(batch['amount'])} ₽; распределено {format_amount(batch['allocated'])} ₽; "
            f"аванс доступен {format_amount(batch['advance'])} ₽"
        )
        for part in item["allocations"]:
            student = escape(person_label(part["client"], part.get("client_contact")))
            lines.append(
                f"  ↳ Передача №{part['assignment_id']}: {student} — {escape(part['tutor'])}; "
                f"распределено {format_amount(part['amount'])} ₽ от {part['allocation_date']}; "
                f"возврат {format_amount(part['refunded'])} ₽"
            )
        if batch["notes"]:
            lines.append(f"  Комментарий: {escape(batch['notes'])}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_payouts_menu())


@router.message(F.text == "⬅️ Главное меню")
async def payment_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())
