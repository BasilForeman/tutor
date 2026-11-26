
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
async def cancel_client_creation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Создание ученика отменено.",
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
async def show_clients(message: Message):
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
