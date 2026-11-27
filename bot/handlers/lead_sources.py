
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.database.connection import async_session
from bot.services.lead_sources import (
    create_lead_source,
    get_lead_sources,
    get_lead_source_by_id,
    update_lead_source,
    archive_lead_source,
)
from bot.keyboards.lead_sources import (
    get_lead_sources_menu,
    get_lead_sources_cancel_keyboard,
)
from bot.keyboards.main_menu import get_main_menu


router = Router()


class LeadSourceForm(StatesGroup):
    name = State()
    search = State()
    edit_id = State()
    edit_name = State()
    archive_id = State()


@router.message(F.text == "📣 Источники")
async def lead_sources_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "📣 Управление источниками\n\nВыбери действие:",
        reply_markup=get_lead_sources_menu(),
    )


@router.message(LeadSourceForm.name, F.text == "❌ Отмена")
@router.message(LeadSourceForm.search, F.text == "❌ Отмена")
@router.message(LeadSourceForm.edit_id, F.text == "❌ Отмена")
@router.message(LeadSourceForm.edit_name, F.text == "❌ Отмена")
@router.message(LeadSourceForm.archive_id, F.text == "❌ Отмена")
async def cancel_source_creation(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await message.answer(
        "Действие с источником отменено.",
        reply_markup=get_lead_sources_menu(),
    )


@router.message(LeadSourceForm.name, F.text == "⬅️ Главное меню")
async def source_back_to_main(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "➕ Добавить источник")
async def start_source_creation(
    message: Message,
    state: FSMContext,
):
    await state.clear()
    await state.set_state(LeadSourceForm.name)

    await message.answer(
        "Введи название источника.\n\n"
        "Например: Telegram — чат преподавателей",
        reply_markup=get_lead_sources_cancel_keyboard(),
    )


@router.message(LeadSourceForm.name)
async def process_source_name(
    message: Message,
    state: FSMContext,
):
    name = (message.text or "").strip()

    if not name:
        await message.answer("Название не может быть пустым.")
        return

    try:
        async with async_session() as session:
            source = await create_lead_source(
                session=session,
                name=name,
            )

    except ValueError as error:
        await message.answer(
            f"⚠️ {error}\n\nВведи другое название:"
        )
        return

    await state.clear()

    await message.answer(
        "✅ Источник добавлен!\n\n"
        f"ID: {source.id}\n"
        f"Название: {source.name}",
        reply_markup=get_lead_sources_menu(),
    )


@router.message(F.text == "📋 Список источников")
async def show_lead_sources(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        sources = await get_lead_sources(session)

    if not sources:
        await message.answer(
            "Пока источников нет.",
            reply_markup=get_lead_sources_menu(),
        )
        return

    lines = ["📋 <b>Список источников:</b>\n"]

    for source in sources:
        lines.append(
            f"<b>{source.id}. {escape(source.name)}</b>"
        )

    await message.answer(
        "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_lead_sources_menu(),
    )


@router.message(F.text == "🗄 Архивные источники")
async def show_archived_sources(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        sources = await get_lead_sources(session, active_only=False)
    if not sources:
        await message.answer("Архивных источников нет.", reply_markup=get_lead_sources_menu())
        return
    cards = [f"<b>#{s.id} {escape(s.name)}</b>" for s in sources[:30]]
    await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_lead_sources_menu())


@router.message(F.text == "🔎 Поиск / карточка источника")
async def source_search_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadSourceForm.search)
    await message.answer("Введи ID или часть названия источника:")


@router.message(LeadSourceForm.search)
async def source_search(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введи ID или поисковый текст.")
        return
    async with async_session() as session:
        if query.isdigit():
            source = await get_lead_source_by_id(session, int(query))
            sources = [source] if source else []
        else:
            sources = await get_lead_sources(session, active_only=False, search=query)
    await state.clear()
    if not sources:
        await message.answer("Источники не найдены.", reply_markup=get_lead_sources_menu())
        return
    cards = [f"<b>#{item.id} {escape(item.name)}</b>\nСтатус: {'Активен' if item.is_active else 'В архиве'}" for item in sources[:20]]
    await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_lead_sources_menu())


@router.message(F.text == "✏️ Изменить источник")
async def source_edit_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadSourceForm.edit_id)
    await message.answer("Введи ID источника для изменения:")


@router.message(LeadSourceForm.edit_id)
async def source_edit_id(message: Message, state: FSMContext):
    try:
        source_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        source = await get_lead_source_by_id(session, source_id)
    if not source or not source.is_active:
        await state.clear()
        await message.answer("Активный источник не найден.", reply_markup=get_lead_sources_menu())
        return
    await state.update_data(source_id=source_id)
    await state.set_state(LeadSourceForm.edit_name)
    await message.answer(f"Текущее название: {escape(source.name)}. Введи новое:")


@router.message(LeadSourceForm.edit_name)
async def source_edit_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым.")
        return
    data = await state.get_data()
    try:
        async with async_session() as session:
            source = await update_lead_source(session, data["source_id"], name)
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(f"✅ Источник #{source.id} обновлён: {escape(source.name)}", parse_mode="HTML", reply_markup=get_lead_sources_menu())


@router.message(F.text == "📦 Архивировать источник")
async def source_archive_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadSourceForm.archive_id)
    await message.answer("Введи ID источника. Исторические заявки сохранят привязку:")


@router.message(LeadSourceForm.archive_id)
async def source_archive(message: Message, state: FSMContext):
    try:
        source_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        archived = await archive_lead_source(session, source_id)
    await state.clear()
    await message.answer("Источник перенесён в архив." if archived else "Активный источник не найден.", reply_markup=get_lead_sources_menu())


@router.message(F.text == "⬅️ Главное меню")
async def sources_back_to_main(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(),
    )
