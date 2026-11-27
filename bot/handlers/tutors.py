from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from html import escape

from bot.database.connection import async_session
from bot.services.tutors import create_tutor, get_tutors, get_tutor_by_id, update_tutor, archive_tutor
from bot.keyboards.tutors import (
    get_tutors_menu,
    get_subject_keyboard,
)
from bot.keyboards.main_menu import get_main_menu


router = Router()


class TutorForm(StatesGroup):
    nickname = State()
    subject = State()
    search = State()
    edit_id = State()
    edit_nickname = State()
    edit_subject = State()
    archive_id = State()


@router.message(F.text == "👨‍🏫 Репетиторы")
async def tutors_menu(message: Message, state: FSMContext):
    await state.clear()
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


@router.message(TutorForm.nickname, F.text == "❌ Отмена")
@router.message(TutorForm.subject, F.text == "❌ Отмена")
@router.message(TutorForm.search, F.text == "❌ Отмена")
@router.message(TutorForm.edit_id, F.text == "❌ Отмена")
@router.message(TutorForm.edit_nickname, F.text == "❌ Отмена")
@router.message(TutorForm.edit_subject, F.text == "❌ Отмена")
@router.message(TutorForm.archive_id, F.text == "❌ Отмена")
async def cancel_tutor_creation(
    message: Message,
    state: FSMContext
):
    await state.clear()

    await message.answer(
        "Действие с репетитором отменено.",
        reply_markup=get_tutors_menu()
    )


@router.message(F.text == "➕ Добавить репетитора")
async def start_tutor_creation(
    message: Message,
    state: FSMContext
):
    await state.clear()
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
async def show_tutors(message: Message, state: FSMContext):
    await state.clear()
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


@router.message(F.text == "🗄 Архивные репетиторы")
async def show_archived_tutors(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        tutors = await get_tutors(session, active_only=False)
    if not tutors:
        await message.answer("Архивных репетиторов нет.", reply_markup=get_tutors_menu())
        return
    cards = [f"<b>#{t.id} {escape(t.nickname)}</b>\nПредмет: {escape(t.subject or 'Не указан')}" for t in tutors[:30]]
    await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_tutors_menu())


@router.message(F.text == "🔎 Поиск / карточка репетитора")
async def tutor_search_start(message: Message, state: FSMContext):
    await state.set_state(TutorForm.search)
    await message.answer("Введи ID, имя или предмет репетитора:")


@router.message(TutorForm.search)
async def tutor_search(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введи ID, имя или предмет текстом.")
        return
    async with async_session() as session:
        try:
            tutor = await get_tutor_by_id(session, int(query)) if query.isdigit() else None
            tutors = [tutor] if tutor else await get_tutors(session, active_only=None, search=query)
        except ValueError:
            tutors = await get_tutors(session, active_only=None, search=query)
    await state.clear()
    if not tutors:
        await message.answer("Репетиторы не найдены.", reply_markup=get_tutors_menu())
        return
    cards = [f"<b>#{item.id} {escape(item.nickname)}</b>\nПредмет: {escape(item.subject or 'Не указан')}\nСтатус: {'Активен' if item.is_active else 'В архиве'}" for item in tutors[:20]]
    await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_tutors_menu())


@router.message(F.text == "✏️ Изменить репетитора")
async def tutor_edit_start(message: Message, state: FSMContext):
    await state.set_state(TutorForm.edit_id)
    await message.answer("Введи ID репетитора для изменения:")


@router.message(TutorForm.edit_id)
async def tutor_edit_id(message: Message, state: FSMContext):
    try:
        tutor_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        tutor = await get_tutor_by_id(session, tutor_id)
    if not tutor or not tutor.is_active:
        await state.clear()
        await message.answer("Активный репетитор с таким ID не найден.", reply_markup=get_tutors_menu())
        return
    await state.update_data(tutor_id=tutor_id)
    await state.set_state(TutorForm.edit_nickname)
    await message.answer(f"Текущее имя: {escape(tutor.nickname)}. Введи новое имя:")


@router.message(TutorForm.edit_nickname)
async def tutor_edit_nickname(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()
    if not nickname:
        await message.answer("Имя не может быть пустым.")
        return
    await state.update_data(nickname=nickname)
    await state.set_state(TutorForm.edit_subject)
    await message.answer("Введи новый предмет или «⏭ Пропустить», чтобы очистить поле:")


@router.message(TutorForm.edit_subject)
async def tutor_edit_subject(message: Message, state: FSMContext):
    data = await state.get_data()
    subject = (message.text or "").strip()
    if not subject:
        await message.answer("Введи предмет или «⏭ Пропустить».")
        return
    try:
        async with async_session() as session:
            tutor = await update_tutor(session, data["tutor_id"], nickname=data["nickname"], subject="" if subject == "⏭ Пропустить" else subject)
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(f"✅ Обновлено: #{tutor.id} {escape(tutor.nickname)} — {escape(tutor.subject or 'предмет не указан')}", parse_mode="HTML", reply_markup=get_tutors_menu())


@router.message(F.text == "📦 Архивировать репетитора")
async def tutor_archive_start(message: Message, state: FSMContext):
    await state.set_state(TutorForm.archive_id)
    await message.answer("Введи ID репетитора для архивирования. Связанные передачи сохранятся:")


@router.message(TutorForm.archive_id)
async def tutor_archive(message: Message, state: FSMContext):
    try:
        tutor_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        archived = await archive_tutor(session, tutor_id)
    await state.clear()
    await message.answer("Репетитор перенесён в архив." if archived else "Активный репетитор не найден.", reply_markup=get_tutors_menu())
