from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu
from bot.services.assignments import create_assignment, create_manual_assignment, get_assignments
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


def lead_choices(items):
    rows = [[KeyboardButton(text="✍️ Ввести данные вручную")]]
    rows.extend([[KeyboardButton(text=f"{item.id} | {f'Заявка №{item.id}, ученик {item.client_id}' }")] for item in items])
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
    await state.update_data(operation_key=uuid4().hex)
    if leads:
        await state.set_state(AssignmentForm.lead_entry_mode)
        await message.answer(
            "Выбери существующую заявку или введи данные вручную. "
            "Если ученик, репетитор или источник уже есть, запись будет повторно использована.",
            reply_markup=lead_choices(leads),
        )
    else:
        await begin_manual_assignment(message, state)


async def begin_manual_assignment(message: Message, state: FSMContext):
    await state.update_data(manual_mode=True)
    await state.set_state(AssignmentForm.manual_tutor_name)
    await message.answer("Введи имя репетитора:", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.lead_entry_mode, F.text == "✍️ Ввести данные вручную")
async def start_manual_assignment(message: Message, state: FSMContext):
    await begin_manual_assignment(message, state)


@router.message(AssignmentForm.lead_entry_mode)
async def choose_existing_lead(message: Message, state: FSMContext):
    if message.text == CANCEL:
        await cancel_manual_assignment(message, state)
        return
    lead_id = parse_id(message.text)
    async with async_session() as session:
        leads = await get_leads(session)
    lead = next((item for item in leads if item.id == lead_id and item.status != "lost"), None)
    if not lead:
        await message.answer("Заявка не найдена. Выбери её кнопкой или введи данные вручную.")
        return
    await state.update_data(lead_id=lead.id, manual_mode=False)
    async with async_session() as session:
        tutors = await get_tutors(session)
    if not tutors:
        await message.answer("Активных репетиторов нет. Введи нового вручную:", reply_markup=text_keyboard(CANCEL))
        await state.update_data(manual_mode=True)
        await state.set_state(AssignmentForm.manual_tutor_name)
        return
    await state.set_state(AssignmentForm.tutor)
    await message.answer("Выбери репетитора:", reply_markup=choices(tutors, lambda item: item.nickname))


@router.message(AssignmentForm.manual_tutor_name, F.text == CANCEL)
@router.message(AssignmentForm.manual_tutor_subject, F.text == CANCEL)
@router.message(AssignmentForm.manual_client_name, F.text == CANCEL)
@router.message(AssignmentForm.manual_client_contact, F.text == CANCEL)
@router.message(AssignmentForm.manual_source_name, F.text == CANCEL)
@router.message(AssignmentForm.manual_subject, F.text == CANCEL)
@router.message(AssignmentForm.lead_entry_mode, F.text == CANCEL)
async def cancel_manual_assignment(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание передачи отменено.", reply_markup=get_main_menu())


@router.message(AssignmentForm.manual_tutor_name)
async def manual_tutor_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя репетитора не может быть пустым.")
        return
    await state.update_data(tutor_name=name)
    await state.set_state(AssignmentForm.manual_tutor_subject)
    await message.answer("Предмет репетитора (или пропусти):", reply_markup=text_keyboard(SKIP, CANCEL))


@router.message(AssignmentForm.manual_tutor_subject)
async def manual_tutor_subject(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if value == CANCEL:
        await cancel_manual_assignment(message, state)
        return
    await state.update_data(tutor_subject=None if value == SKIP else value)
    await state.set_state(AssignmentForm.manual_client_name)
    await message.answer("Имя ученика:", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.manual_client_name)
async def manual_client_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя ученика не может быть пустым.")
        return
    await state.update_data(client_name=name)
    await state.set_state(AssignmentForm.manual_client_contact)
    await message.answer("Контакт ученика или родителя (или пропусти):", reply_markup=text_keyboard(SKIP, CANCEL))


@router.message(AssignmentForm.manual_client_contact)
async def manual_client_contact(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if value == CANCEL:
        await cancel_manual_assignment(message, state)
        return
    await state.update_data(client_contact=None if value == SKIP else value)
    await state.set_state(AssignmentForm.manual_source_name)
    await message.answer("Источник заявки (например, рекомендация или сайт):", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.manual_source_name)
async def manual_source_name(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value:
        await message.answer("Источник не может быть пустым.")
        return
    await state.update_data(source_name=value)
    await state.set_state(AssignmentForm.manual_subject)
    await message.answer("Предмет или запрос ученика (или пропусти):", reply_markup=text_keyboard(SKIP, CANCEL))


@router.message(AssignmentForm.manual_subject)
async def manual_subject(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if value == CANCEL:
        await cancel_manual_assignment(message, state)
        return
    await state.update_data(subject=None if value == SKIP else value)
    await state.set_state(AssignmentForm.assigned_by)
    await message.answer("Кто передал ученика? Укажи имя или название источника:", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.lead, F.text == CANCEL)
@router.message(AssignmentForm.tutor, F.text == CANCEL)
@router.message(AssignmentForm.assigned_by, F.text == CANCEL)
@router.message(AssignmentForm.rate, F.text == CANCEL)
@router.message(AssignmentForm.commission_mode, F.text == CANCEL)
@router.message(AssignmentForm.commission_multiplier, F.text == CANCEL)
@router.message(AssignmentForm.commission_amount, F.text == CANCEL)
@router.message(AssignmentForm.commission_percentage, F.text == CANCEL)
@router.message(AssignmentForm.subscription_purchase_date, F.text == CANCEL)
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
    await state.set_state(AssignmentForm.commission_mode)
    await message.answer(
        "Выбери условия комиссии:",
        reply_markup=text_keyboard("По множителю ставки", "Фиксированная сумма", "Вручную", "Абонемент", "Процент от заработка", CANCEL),
    )


@router.message(AssignmentForm.commission_mode)
async def select_commission_mode(message: Message, state: FSMContext):
    modes = {
        "По множителю ставки": "rate_multiplier",
        "Фиксированная сумма": "fixed",
        "Вручную": "manual",
        "Абонемент": "subscription",
        "Процент от заработка": "percent",
    }
    mode = modes.get((message.text or "").strip())
    if not mode:
        await message.answer("Выбери режим кнопкой.")
        return
    await state.update_data(commission_mode=mode)
    if mode == "rate_multiplier":
        await state.set_state(AssignmentForm.commission_multiplier)
        await message.answer("Введи множитель ставки (обычно 4; возможны 2 или 2,5):", reply_markup=text_keyboard("4", CANCEL))
    elif mode == "percent":
        await state.set_state(AssignmentForm.commission_percentage)
        await message.answer("Какой процент комиссии от заработка по платным проведённым занятиям? Введи от 0 до 100:", reply_markup=text_keyboard(CANCEL))
    else:
        await state.set_state(AssignmentForm.commission_amount)
        await message.answer("Введи согласованную сумму комиссии:", reply_markup=text_keyboard(CANCEL))


@router.message(AssignmentForm.commission_amount)
async def enter_commission_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечную неотрицательную сумму.")
        return
    await state.update_data(commission_amount=str(amount))
    data = await state.get_data()
    if data["commission_mode"] == "subscription":
        await state.set_state(AssignmentForm.subscription_purchase_date)
        await message.answer("Дата покупки абонемента (ГГГГ-ММ-ДД):", reply_markup=text_keyboard(CANCEL))
        return
    await ask_assignment_due_date(message, state)


@router.message(AssignmentForm.commission_percentage)
async def enter_commission_percentage(message: Message, state: FSMContext):
    try:
        percentage = Decimal((message.text or "").strip().replace(",", "."))
        if not percentage.is_finite() or percentage <= 0 or percentage > 100:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи процент больше 0 и не больше 100.")
        return
    await state.update_data(commission_percentage=str(percentage), commission_amount="0.00")
    await ask_assignment_due_date(message, state)


@router.message(AssignmentForm.subscription_purchase_date)
async def enter_subscription_purchase_date(message: Message, state: FSMContext):
    try:
        purchase_date = date.fromisoformat((message.text or "").strip())
    except ValueError:
        await message.answer("Введи дату покупки абонемента как ГГГГ-ММ-ДД.")
        return
    await state.update_data(subscription_purchase_date=purchase_date.isoformat())
    await ask_assignment_due_date(message, state)


async def ask_assignment_due_date(message: Message, state: FSMContext):
    await state.set_state(AssignmentForm.payment_due_date)
    await message.answer("Срок оплаты комиссии в формате ГГГГ-ММ-ДД или пропусти:", reply_markup=text_keyboard(SKIP, CANCEL))


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
        commission_mode="rate_multiplier",
        commission_multiplier=str(multiplier),
        commission_amount=str(commission_amount),
    )
    await ask_assignment_due_date(message, state)


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
    lead_label = (
        f"Ученик: {escape(data['client_name'])}; предмет: {escape(data.get('subject') or 'не указан')}"
        if data.get("manual_mode") else f"Заявка: №{data['lead_id']}"
    )
    await message.answer(
        "Проверь передачу:\n"
        f"{lead_label}\n"
        f"Репетитор: {escape(data['tutor_name'])}\n"
        f"Ставка: {data['rate']}\n"
        f"Комиссия: {_commission_summary(data)}\n"
        f"Срок оплаты: {due_label}\n\n"
        "Создать запись?",
        reply_markup=text_keyboard("✅ Подтвердить", CANCEL),
    )


@router.message(AssignmentForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_assignment(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session() as session:
            if data.get("manual_mode"):
                assignment, created = await create_manual_assignment(
                    session=session,
                    tutor_name=data["tutor_name"],
                    tutor_subject=data.get("tutor_subject"),
                    client_name=data["client_name"],
                    client_contact=data.get("client_contact"),
                    source_name=data["source_name"],
                    subject=data.get("subject"),
                    assigned_by=data["assigned_by"],
                    rate=Decimal(data["rate"]),
                    commission_multiplier=Decimal(data["commission_multiplier"]) if data.get("commission_multiplier") else None,
                    commission_mode=data["commission_mode"],
                    commission_amount=Decimal(data["commission_amount"]),
                    commission_percentage=Decimal(data["commission_percentage"]) if data.get("commission_percentage") else None,
                    subscription_purchase_date=date.fromisoformat(data["subscription_purchase_date"]) if data.get("subscription_purchase_date") else None,
                    operation_key=data["operation_key"],
                    payment_due_date=date.fromisoformat(data["payment_due_date"]) if data["payment_due_date"] else None,
                )
            else:
                assignment = await create_assignment(
                    session=session,
                    lead_id=data["lead_id"],
                    tutor_id=data["tutor_id"],
                    assigned_by=data["assigned_by"],
                    rate=Decimal(data["rate"]),
                    commission_multiplier=Decimal(data["commission_multiplier"]) if data.get("commission_multiplier") else None,
                    commission_mode=data["commission_mode"],
                    commission_amount=Decimal(data["commission_amount"]),
                    commission_percentage=Decimal(data["commission_percentage"]) if data.get("commission_percentage") else None,
                    subscription_purchase_date=date.fromisoformat(data["subscription_purchase_date"]) if data.get("subscription_purchase_date") else None,
                    operation_key=data["operation_key"],
                    payment_due_date=date.fromisoformat(data["payment_due_date"]) if data["payment_due_date"] else None,
                )
                created = None
    except ValueError as error:
        await state.clear()
        await message.answer(f"⚠️ {error}", reply_markup=get_main_menu())
        return
    await state.clear()
    detail = ""
    if created:
        detail = "\n" + ", ".join(
            label for key, label in (("tutor", "репетитор"), ("client", "ученик"), ("source", "источник"), ("lead", "заявка"))
            if created[key]
        )
        detail = f"\nДобавлены новые записи: {detail[1:]}" if detail != "\n" else "\nИспользованы существующие записи."
    await message.answer(
        f"✅ Передача №{assignment.id} создана.{detail}",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "📋 Список передач")
async def list_assignments(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        assignments = await get_assignments(session)
    if not assignments:
        await message.answer("Передач пока нет.", reply_markup=get_main_menu())
        return
    lines = ["<b>Последние передачи:</b>"]
    for item in assignments[:30]:
        terms = _commission_summary({
            "commission_mode": item.commission_mode,
            "commission_amount": str(item.commission_amount),
            "commission_multiplier": str(item.commission_multiplier),
            "commission_percentage": str(item.commission_percentage or ""),
            "subscription_purchase_date": item.subscription_purchase_date.isoformat() if item.subscription_purchase_date else "",
        })
        lines.append(
            f"№{item.id} | заявка №{item.lead_id} | репетитор №{item.tutor_id} | "
            f"ученик №{item.client_id} | комиссия: {escape(terms)}"
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
        commission_mode=assignment.commission_mode,
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
        _close_confirmation_text(data, limit),
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


def _commission_summary(data):
    mode = data["commission_mode"]
    if mode == "rate_multiplier":
        return f"{data['commission_multiplier']} ставки = {data['commission_amount']}"
    if mode == "percent":
        return f"{data['commission_percentage']}% от заработка за платные проведённые занятия"
    if mode == "subscription":
        return f"абонемент {data['commission_amount']}, покупка {data['subscription_purchase_date']}"
    return f"{data['commission_amount']} ({'фиксированная' if mode == 'fixed' else 'вручную'})"


def _close_confirmation_text(data, lesson_limit):
    message = "Подтвердить закрытие передачи?"
    if data["commission_mode"] == "rate_multiplier":
        message += f" Если проведено не больше {lesson_limit} платных занятий, комиссия станет 25% фактического заработка."
    elif data["commission_mode"] == "percent":
        message += " Итоговая комиссия зафиксируется по фактическому заработку и согласованному проценту."
    else:
        message += " Согласованная комиссия будет сохранена."
    return message
