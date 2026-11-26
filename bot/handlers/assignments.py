from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu
from bot.services.assignments import create_assignment, get_assignments
from bot.services.finance import close_assignment
from bot.services.leads import get_leads
from bot.services.tutors import get_tutors
from bot.states.assignments import AssignmentForm

router = Router()
CANCEL = "❌ Отмена"
SKIP = "⏭ Пропустить"


def choices(items, label):
    rows = [[KeyboardButton(text=f"{item.id} | {label(item)}")] for item in items]
    rows.append([KeyboardButton(text=CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def text_keyboard(*buttons):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=button)] for button in buttons],
        resize_keyboard=True,
    )


def parse_id(text):
    try:
        return int((text or "").split("|", 1)[0].strip())
    except ValueError:
        return None


@router.message(F.text == "➕ Новая передача")
async def start_assignment(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        leads = await get_leads(session)
    leads = [lead for lead in leads if lead.status != "lost"]
    if not leads:
        await message.answer("Нет активных заявок для передачи.", reply_markup=get_main_menu())
        return
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(AssignmentForm.lead)
    await message.answer(
        "Выбери заявку. Повторная передача создаст отдельную запись:",
        reply_markup=choices(leads, lambda item: f"Заявка №{item.id}, ученик {item.client_id}"),
    )


@router.message(AssignmentForm.lead, F.text == CANCEL)
@router.message(AssignmentForm.tutor, F.text == CANCEL)
@router.message(AssignmentForm.assigned_by, F.text == CANCEL)
@router.message(AssignmentForm.rate, F.text == CANCEL)
@router.message(AssignmentForm.commission_multiplier, F.text == CANCEL)
@router.message(AssignmentForm.payment_due_date, F.text == CANCEL)
@router.message(AssignmentForm.confirmation, F.text == CANCEL)
@router.message(AssignmentForm.close_assignment, F.text == CANCEL)
@router.message(AssignmentForm.close_reason, F.text == CANCEL)
@router.message(AssignmentForm.close_confirmation, F.text == CANCEL)
async def cancel_assignment(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание передачи отменено.", reply_markup=get_main_menu())


@router.message(AssignmentForm.lead)
async def select_lead(message: Message, state: FSMContext):
    lead_id = parse_id(message.text)
    async with async_session() as session:
        leads = await get_leads(session)
    lead = next((item for item in leads if item.id == lead_id and item.status != "lost"), None)
    if not lead:
        await message.answer("Заявка не найдена. Выбери её кнопкой.")
        return
    await state.update_data(lead_id=lead.id)
    async with async_session() as session:
        tutors = await get_tutors(session)
    if not tutors:
        await state.clear()
        await message.answer("Сначала добавь репетитора.", reply_markup=get_main_menu())
        return
    await state.set_state(AssignmentForm.tutor)
    await message.answer("Выбери репетитора:", reply_markup=choices(tutors, lambda item: item.nickname))


@router.message(AssignmentForm.tutor)
async def select_tutor(message: Message, state: FSMContext):
    tutor_id = parse_id(message.text)
    async with async_session() as session:
        tutors = await get_tutors(session)
    tutor = next((item for item in tutors if item.id == tutor_id), None)
    if not tutor:
        await message.answer("Репетитор не найден. Выбери его кнопкой.")
        return
    await state.update_data(tutor_id=tutor.id, tutor_name=tutor.nickname)
    await state.set_state(AssignmentForm.assigned_by)
    await message.answer("Кто передал ученика?", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.assigned_by)
async def enter_assigner(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value:
        await message.answer("Укажи, кто передал ученика.")
        return
    await state.update_data(assigned_by=value)
    await state.set_state(AssignmentForm.rate)
    await message.answer("Введи стоимость одного занятия (например 1500):", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.rate)
async def enter_rate(message: Message, state: FSMContext):
    try:
        rate = Decimal((message.text or "").strip().replace(",", "."))
        if not rate.is_finite() or rate <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Нужна конечная сумма больше нуля. Например: 1500")
        return
    await state.update_data(rate=str(rate))
    await state.set_state(AssignmentForm.commission_multiplier)
    await message.answer("Введи множитель ставки (обычно 4; возможны 2 или 2,5):", reply_markup=text_keyboard("4", CANCEL))


@router.message(AssignmentForm.commission_multiplier)
async def enter_commission_multiplier(message: Message, state: FSMContext):
    try:
        multiplier = Decimal((message.text or "").strip().replace(",", "."))
        if not multiplier.is_finite() or multiplier <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечный положительный множитель, например 4 или 2,5.")
        return
    data = await state.get_data()
    commission_amount = (Decimal(data["rate"]) * multiplier).quantize(Decimal("0.01"))
    await state.update_data(
        commission_multiplier=str(multiplier),
        commission_amount=str(commission_amount),
    )
    await state.set_state(AssignmentForm.payment_due_date)
    await message.answer("Срок оплаты в формате ГГГГ-ММ-ДД или пропусти:", reply_markup=text_keyboard(SKIP, CANCEL))


@router.message(AssignmentForm.payment_due_date, F.text == SKIP)
@router.message(AssignmentForm.payment_due_date)
async def enter_due_date(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    due_date = None
    if value != SKIP:
        try:
            due_date = date.fromisoformat(value)
        except ValueError:
            await message.answer("Введи дату как ГГГГ-ММ-ДД или нажми «Пропустить».")
            return
    await state.update_data(payment_due_date=due_date.isoformat() if due_date else None)
    data = await state.get_data()
    await state.set_state(AssignmentForm.confirmation)
    due_label = data["payment_due_date"] or "не установлен"
    await message.answer(
        "Проверь передачу:\n"
        f"Заявка: №{data['lead_id']}\n"
        f"Репетитор: {escape(data['tutor_name'])}\n"
        f"Ставка: {data['rate']}\n"
        f"Комиссия: {data['commission_multiplier']} ставки = {data['commission_amount']}\n"
        f"Срок оплаты: {due_label}\n\n"
        "Создать запись?",
        reply_markup=text_keyboard("✅ Подтвердить", CANCEL),
    )


@router.message(AssignmentForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_assignment(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        assignment = await create_assignment(
            session=session,
            lead_id=data["lead_id"],
            tutor_id=data["tutor_id"],
            assigned_by=data["assigned_by"],
            rate=Decimal(data["rate"]),
            commission_multiplier=Decimal(data["commission_multiplier"]),
            operation_key=data["operation_key"],
            payment_due_date=(
                date.fromisoformat(data["payment_due_date"])
                if data["payment_due_date"] else None
            ),
        )
    await state.clear()
    await message.answer(
        f"✅ Передача №{assignment.id} создана.",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "📋 Список передач")
async def list_assignments(message: Message):
    async with async_session() as session:
        assignments = await get_assignments(session)
    if not assignments:
        await message.answer("Передач пока нет.", reply_markup=get_main_menu())
        return
    lines = ["<b>Последние передачи:</b>"]
    for item in assignments[:30]:
        lines.append(
            f"№{item.id} | заявка №{item.lead_id} | репетитор №{item.tutor_id} | "
            f"ученик №{item.client_id} | комиссия {item.commission_amount}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_menu())


@router.message(F.text == "🔚 Завершить обучение")
async def start_close_assignment(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        assignments = await get_assignments(session)
    open_assignments = [item for item in assignments if not item.is_closed]
    if not open_assignments:
        await message.answer("Нет открытых передач.", reply_markup=get_main_menu())
        return
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(AssignmentForm.close_assignment)
    await message.answer(
        "Выбери передачу, обучение по которой завершилось:",
        reply_markup=choices(open_assignments, lambda item: f"Передача №{item.id}, ученик {item.client_id}"),
    )


@router.message(AssignmentForm.close_assignment)
async def select_close_assignment(message: Message, state: FSMContext):
    assignment_id = parse_id(message.text)
    async with async_session() as session:
        assignments = await get_assignments(session)
    assignment = next((item for item in assignments if item.id == assignment_id and not item.is_closed), None)
    if not assignment:
        await message.answer("Открытая передача не найдена. Выбери её кнопкой.")
        return
    await state.update_data(
        assignment_id=assignment.id,
        short_term_lesson_limit=assignment.short_term_lesson_limit,
    )
    await state.set_state(AssignmentForm.close_reason)
    await message.answer("Укажи причину завершения обучения:", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.close_reason)
async def enter_close_reason(message: Message, state: FSMContext):
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой.")
        return
    await state.update_data(close_reason=reason)
    await state.set_state(AssignmentForm.close_confirmation)
    data = await state.get_data()
    limit = data["short_term_lesson_limit"]
    await message.answer(
        f"Подтвердить закрытие передачи? Если проведено не больше {limit} платных занятий, комиссия пересчитается как 25% фактического заработка.",
        reply_markup=text_keyboard("✅ Подтвердить", CANCEL),
    )


@router.message(AssignmentForm.close_confirmation, F.text == "✅ Подтвердить")
async def confirm_close_assignment(message: Message, state: FSMContext):
    data = await state.get_data()
    author = message.from_user.full_name if message.from_user else "Telegram admin"
    try:
        async with async_session() as session:
            assignment, adjustment = await close_assignment(
                session=session,
                assignment_id=data["assignment_id"],
                reason=data["close_reason"],
                author=author,
                operation_key=data["operation_key"],
            )
    except ValueError as error:
        await state.clear()
        await message.answer(f"⚠️ {error}", reply_markup=get_main_menu())
        return
    await state.clear()
    if adjustment:
        outcome = f"Итоговая комиссия после перерасчёта: {adjustment.new_amount}."
    else:
        outcome = f"Согласованная комиссия к оплате: {assignment.commission_amount}."
    await message.answer(
        f"✅ Передача №{assignment.id} закрыта. {outcome}",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "⬅️ Главное меню")
async def assignment_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())
