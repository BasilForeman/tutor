from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from html import escape

from bot.database.connection import async_session
from bot.services.tutors import create_tutor, get_tutors
from bot.keyboards.tutors import (
    get_tutors_menu,
    get_subject_keyboard,
)
from bot.keyboards.main_menu import get_main_menu


router = Router()


class TutorForm(StatesGroup):
    nickname = State()
    subject = State()


@router.message(F.text == "👨‍🏫 Репетиторы")
async def tutors_menu(message: Message):
    await message.answer(
        "👨‍🏫 Управление репетиторами\n\nВыбери действие:",
        reply_markup=get_tutors_menu()
    )


@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu()
    )


@router.message(F.text == "❌ Отмена")
async def cancel_tutor_creation(
    message: Message,
    state: FSMContext
):
    await state.clear()

    await message.answer(
        "Создание репетитора отменено.",
        reply_markup=get_tutors_menu()
    )


@router.message(F.text == "➕ Добавить репетитора")
async def start_tutor_creation(
    message: Message,
    state: FSMContext
):
    await state.set_state(TutorForm.nickname)

    await message.answer(
        "Введи имя или никнейм репетитора:"
    )


@router.message(TutorForm.nickname)
async def process_tutor_nickname(
    message: Message,
    state: FSMContext
):
    nickname = (message.text or "").strip()

    if not nickname:
        await message.answer("Имя не может быть пустым. Попробуй ещё раз.")
        return

    await state.update_data(nickname=nickname)
    await state.set_state(TutorForm.subject)

    await message.answer(
        f"Репетитор: {nickname}\n\n"
        "Теперь введи предмет преподавания "
        "или нажми «Пропустить предмет».",
        reply_markup=get_subject_keyboard()
    )


@router.message(TutorForm.subject)
async def process_tutor_subject(
    message: Message,
    state: FSMContext
):
    subject = (message.text or "").strip()

    if subject == "Пропустить предмет":
        subject = None

    elif not subject:
        await message.answer("Введи предмет или нажми кнопку пропуска.")
        return

    data = await state.get_data()
    nickname = data["nickname"]

    try:
        async with async_session() as session:
            tutor = await create_tutor(
                session=session,
                nickname=nickname,
                subject=subject,
            )

    except ValueError as error:
        await state.clear()
        await message.answer(
            f"⚠️ {error}",
            reply_markup=get_tutors_menu()
        )
        return

    await state.clear()

    await message.answer(
        "✅ Репетитор успешно добавлен!\n\n"
        f"ID: {tutor.id}\n"
        f"Имя: {tutor.nickname}\n"
        f"Предмет: {tutor.subject or 'Не указан'}",
        reply_markup=get_tutors_menu()
    )


@router.message(F.text == "📋 Список репетиторов")
async def show_tutors(message: Message):
    async with async_session() as session:
        tutors = await get_tutors(session)

    if not tutors:
        await message.answer(
            "Пока репетиторов нет.",
            reply_markup=get_tutors_menu()
        )
        return

    lines = ["📋 <b>Список репетиторов:</b>\n"]

    for tutor in tutors:
        lines.append(
            f"<b>{tutor.id}. {escape(tutor.nickname)}</b>\n"
            f"Предмет: {escape(tutor.subject or 'Не указан')}"
        )

    await message.answer(
        "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_tutors_menu()
    )
