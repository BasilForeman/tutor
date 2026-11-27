from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.database.connection import async_session
from bot.keyboards.main_menu import get_main_menu, get_lessons_menu
from bot.services.assignments import get_assignments
from bot.services.lessons import create_lesson
from bot.states.lessons import LessonForm

router = Router()
CANCEL = "❌ Отмена"


def keyboard(values):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=value)] for value in values],
        resize_keyboard=True,
    )


@router.message(F.text == "📚 Занятия")
async def open_lessons_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Учёт занятий:", reply_markup=get_lessons_menu())


@router.message(F.text == "➕ Записать занятие")
async def start_lesson(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        assignments = await get_assignments(session)
    if not assignments:
        await message.answer("Сначала создай передачу.", reply_markup=get_main_menu())
        return
    rows = [f"{item.id} | ученик {item.client_id}, репетитор {item.tutor_id}" for item in assignments]
    rows.append(CANCEL)
    await state.update_data(operation_key=uuid4().hex)
    await state.set_state(LessonForm.assignment)
    await message.answer("Выбери передачу:", reply_markup=keyboard(rows))


@router.message(LessonForm.assignment, F.text == CANCEL)
@router.message(LessonForm.lesson_type, F.text == CANCEL)
@router.message(LessonForm.status, F.text == CANCEL)
@router.message(LessonForm.lesson_date, F.text == CANCEL)
@router.message(LessonForm.amount, F.text == CANCEL)
@router.message(LessonForm.notes, F.text == CANCEL)
@router.message(LessonForm.confirmation, F.text == CANCEL)
async def cancel_lesson(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Регистрация занятия отменена.", reply_markup=get_main_menu())


@router.message(LessonForm.assignment)
async def choose_assignment(message: Message, state: FSMContext):
    try:
        assignment_id = int((message.text or "").split("|", 1)[0].strip())
    except ValueError:
        await message.answer("Выбери передачу кнопкой.")
        return
    async with async_session() as session:
        assignments = await get_assignments(session)
    if not any(item.id == assignment_id for item in assignments):
        await message.answer("Передача не найдена. Выбери её кнопкой.")
        return
    await state.update_data(assignment_id=assignment_id)
    await state.set_state(LessonForm.lesson_type)
    await message.answer("Тип занятия:", reply_markup=keyboard(["Платное", "Пробное", CANCEL]))


@router.message(LessonForm.lesson_type)
async def choose_lesson_type(message: Message, state: FSMContext):
    lesson_type = {"Платное": "paid", "Пробное": "trial"}.get(message.text or "")
    if not lesson_type:
        await message.answer("Выбери «Платное» или «Пробное».")
        return
    await state.update_data(lesson_type=lesson_type)
    await state.set_state(LessonForm.status)
    await message.answer("Статус занятия:", reply_markup=keyboard(["Проведено", "Отменено", CANCEL]))


@router.message(LessonForm.status)
async def choose_status(message: Message, state: FSMContext):
    status = {"Проведено": "completed", "Отменено": "cancelled"}.get(message.text or "")
    if not status:
        await message.answer("Выбери «Проведено» или «Отменено».")
        return
    await state.update_data(status=status)
    await state.set_state(LessonForm.lesson_date)
    await message.answer(
        "Дата занятия в формате ГГГГ-ММ-ДД:",
        reply_markup=keyboard([date.today().isoformat(), CANCEL]),
    )


@router.message(LessonForm.lesson_date)
async def enter_date(message: Message, state: FSMContext):
    try:
        lesson_date = date.fromisoformat((message.text or "").strip())
    except ValueError:
        await message.answer("Введи дату в формате ГГГГ-ММ-ДД.")
        return
    await state.update_data(lesson_date=lesson_date.isoformat())
    data = await state.get_data()
    if data["lesson_type"] == "paid" and data["status"] == "completed":
        await state.set_state(LessonForm.amount)
        await message.answer("Сколько репетитор заработал за занятие?")
        return
    await state.update_data(amount=None)
    await state.set_state(LessonForm.notes)
    await message.answer("Комментарий или кнопка «Пропустить»:", reply_markup=keyboard(["⏭ Пропустить", CANCEL]))


@router.message(LessonForm.amount)
async def enter_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введи конечную сумму больше нуля.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(LessonForm.notes)
    await message.answer("Комментарий или кнопка «Пропустить»:", reply_markup=keyboard(["⏭ Пропустить", CANCEL]))


@router.message(LessonForm.notes, F.text == "⏭ Пропустить")
@router.message(LessonForm.notes)
async def enter_notes(message: Message, state: FSMContext):
    notes = None if message.text == "⏭ Пропустить" else (message.text or "").strip() or None
    await state.update_data(notes=notes)
    data = await state.get_data()
    await state.set_state(LessonForm.confirmation)
    await message.answer(
        f"Подтвердить занятие по передаче №{data['assignment_id']}?\n"
        f"Тип: {data['lesson_type']} | статус: {data['status']}\n"
        f"Дата: {data['lesson_date']} | заработок: {data.get('amount') or '—'}",
        reply_markup=keyboard(["✅ Подтвердить", CANCEL]),
    )


@router.message(LessonForm.confirmation, F.text == "✅ Подтвердить")
async def confirm_lesson(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session() as session:
            lesson = await create_lesson(
                session=session,
                assignment_id=data["assignment_id"],
                lesson_type=data["lesson_type"],
                status=data["status"],
                lesson_date=date.fromisoformat(data["lesson_date"]),
                amount=Decimal(data["amount"]) if data.get("amount") is not None else None,
                operation_key=data["operation_key"],
                notes=data.get("notes"),
            )
    except ValueError as error:
        await state.clear()
        await message.answer(f"⚠️ {error}", reply_markup=get_main_menu())
        return
    await state.clear()
    await message.answer(f"✅ Занятие №{lesson.id} записано.", reply_markup=get_main_menu())


@router.message(F.text == "⬅️ Главное меню")
async def lesson_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())
