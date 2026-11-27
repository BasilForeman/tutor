
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from html import escape

from bot.database.connection import async_session
from bot.services.clients import (
    create_client,
    get_clients,
    get_client_by_id,
    archive_client,
    update_client,
)
from bot.keyboards.clients import (
    get_clients_menu,
    get_clients_cancel_keyboard,
    get_clients_skip_keyboard,
)
from bot.keyboards.main_menu import get_main_menu


router = Router()


class ClientForm(StatesGroup):
    nickname = State()
    contact = State()
    notes = State()
    search = State()
    edit_id = State()
    edit_nickname = State()
    edit_contact = State()
    edit_notes = State()
    archive_id = State()


@router.message(F.text == "👨‍🎓 Ученики")
async def clients_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👨‍🎓 Управление учениками\n\nВыбери действие:",
        reply_markup=get_clients_menu(),
    )


@router.message(F.text == "⬅️ Главное меню")
async def clients_back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(),
    )


@router.message(ClientForm.nickname, F.text == "❌ Отмена")
@router.message(ClientForm.contact, F.text == "❌ Отмена")
@router.message(ClientForm.notes, F.text == "❌ Отмена")
@router.message(ClientForm.search, F.text == "❌ Отмена")
@router.message(ClientForm.edit_id, F.text == "❌ Отмена")
@router.message(ClientForm.edit_nickname, F.text == "❌ Отмена")
@router.message(ClientForm.edit_contact, F.text == "❌ Отмена")
@router.message(ClientForm.edit_notes, F.text == "❌ Отмена")
@router.message(ClientForm.archive_id, F.text == "❌ Отмена")
async def cancel_client_creation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие с учеником отменено.",
        reply_markup=get_clients_menu(),
    )


@router.message(F.text == "➕ Добавить ученика")
async def start_client_creation(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClientForm.nickname)

    await message.answer(
        "Введи имя или никнейм ученика:",
        reply_markup=get_clients_cancel_keyboard(),
    )


@router.message(ClientForm.nickname)
async def process_client_nickname(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()

    if not nickname:
        await message.answer("Имя не может быть пустым. Попробуй ещё раз.")
        return

    await state.update_data(nickname=nickname)
    await state.set_state(ClientForm.contact)

    await message.answer(
        f"Ученик: {nickname}\n\n"
        "Введи контакт ученика (Telegram, телефон) "
        "или пропусти этот шаг.",
        reply_markup=get_clients_skip_keyboard(),
    )


@router.message(ClientForm.contact)
async def process_client_contact(message: Message, state: FSMContext):
    contact = (message.text or "").strip()

    if contact == "⏭ Пропустить":
        contact = None

    elif not contact:
        await message.answer("Введи контакт или нажми «Пропустить».")
        return

    await state.update_data(contact=contact)
    await state.set_state(ClientForm.notes)

    await message.answer(
        "Добавь примечание об ученике или пропусти этот шаг.",
        reply_markup=get_clients_skip_keyboard(),
    )


@router.message(ClientForm.notes)
async def process_client_notes(message: Message, state: FSMContext):
    notes = (message.text or "").strip()

    if notes == "⏭ Пропустить":
        notes = None

    elif not notes:
        await message.answer("Введи примечание или нажми «Пропустить».")
        return

    data = await state.get_data()

    try:
        async with async_session() as session:
            client = await create_client(
                session=session,
                nickname=data["nickname"],
                contact=data.get("contact"),
                notes=notes,
            )

    except ValueError as error:
        await state.clear()
        await message.answer(
            f"⚠️ {error}",
            reply_markup=get_clients_menu(),
        )
        return

    await state.clear()

    await message.answer(
        "✅ Ученик успешно добавлен!\n\n"
        f"ID: {client.id}\n"
        f"Имя: {client.nickname}\n"
        f"Контакт: {client.contact or 'Не указан'}\n"
        f"Примечание: {client.notes or 'Нет'}",
        reply_markup=get_clients_menu(),
    )


@router.message(F.text == "📋 Список учеников")
async def show_clients(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        clients = await get_clients(session)

    if not clients:
        await message.answer(
            "Пока учеников нет.",
            reply_markup=get_clients_menu(),
        )
        return

    lines = ["📋 <b>Список учеников:</b>\n"]

    for client in clients:
        lines.append(
            f"<b>{client.id}. {escape(client.nickname)}</b>\n"
            f"Контакт: {escape(client.contact or 'Не указан')}"
        )

    await message.answer(
        "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_clients_menu(),
    )


@router.message(F.text == "🗄 Архивные ученики")
async def show_archived_clients(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        clients = await get_clients(session, active_only=False)
    if not clients:
        await message.answer("Архивных учеников нет.", reply_markup=get_clients_menu())
        return
    cards = [f"<b>#{c.id} {escape(c.nickname)}</b>\nКонтакт: {escape(c.contact or 'Не указан')}" for c in clients[:30]]
    await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_clients_menu())


@router.message(F.text == "🔎 Поиск / карточка ученика")
async def client_search_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClientForm.search)
    await message.answer("Введи ID, имя, контакт или примечание ученика:")


@router.message(ClientForm.search)
async def client_search(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введи ID или поисковый текст.")
        return
    async with async_session() as session:
        if query.isdigit():
            client = await get_client_by_id(session, int(query))
            clients = [client] if client else []
        else:
            clients = await get_clients(session, active_only=None, search=query)
    await state.clear()
    if not clients:
        await message.answer("Ученики не найдены.", reply_markup=get_clients_menu())
        return
    cards = [f"<b>#{c.id} {escape(c.nickname)}</b>\nКонтакт: {escape(c.contact or 'Не указан')}\nПримечание: {escape(c.notes or 'Нет')}\nСтатус: {'Активен' if c.is_active else 'В архиве'}" for c in clients[:20]]
    await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_clients_menu())


@router.message(F.text == "✏️ Изменить ученика")
async def client_edit_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClientForm.edit_id)
    await message.answer("Введи ID ученика для изменения:")


@router.message(ClientForm.edit_id)
async def client_edit_id(message: Message, state: FSMContext):
    try:
        client_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        client = await get_client_by_id(session, client_id)
    if not client or not client.is_active:
        await state.clear()
        await message.answer("Активный ученик не найден.", reply_markup=get_clients_menu())
        return
    await state.update_data(client_id=client_id)
    await state.set_state(ClientForm.edit_nickname)
    await message.answer(f"Текущее имя: {escape(client.nickname)}. Введи новое имя:")


@router.message(ClientForm.edit_nickname)
async def client_edit_nickname(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()
    if not nickname:
        await message.answer("Имя не может быть пустым.")
        return
    await state.update_data(nickname=nickname)
    await state.set_state(ClientForm.edit_contact)
    await message.answer("Введи контакт или «⏭ Пропустить», чтобы очистить его:")


@router.message(ClientForm.edit_contact)
async def client_edit_contact(message: Message, state: FSMContext):
    contact = (message.text or "").strip()
    if not contact:
        await message.answer("Введи контакт или «⏭ Пропустить».")
        return
    await state.update_data(contact="" if contact == "⏭ Пропустить" else contact)
    await state.set_state(ClientForm.edit_notes)
    await message.answer("Введи примечание или «⏭ Пропустить», чтобы очистить его:")


@router.message(ClientForm.edit_notes)
async def client_edit_notes(message: Message, state: FSMContext):
    notes = (message.text or "").strip()
    if not notes:
        await message.answer("Введи примечание или «⏭ Пропустить».")
        return
    data = await state.get_data()
    async with async_session() as session:
        try:
            client = await update_client(session, data["client_id"], nickname=data["nickname"], contact=data["contact"], notes="" if notes == "⏭ Пропустить" else notes)
        except ValueError as error:
            await message.answer(str(error))
            return
    await state.clear()
    await message.answer(f"✅ Карточка ученика #{client.id} обновлена.", reply_markup=get_clients_menu())


@router.message(F.text == "📦 Архивировать ученика")
async def client_archive_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClientForm.archive_id)
    await message.answer("Введи ID ученика. Связанные заявки и передачи сохранятся:")


@router.message(ClientForm.archive_id)
async def client_archive(message: Message, state: FSMContext):
    try:
        client_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        archived = await archive_client(session, client_id)
    await state.clear()
    await message.answer("Ученик перенесён в архив." if archived else "Активный ученик не найден.", reply_markup=get_clients_menu())
