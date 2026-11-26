
from aiogram import Router, F
from aiogram.types import Message
from html import escape
from aiogram.fsm.context import FSMContext

from bot.database.connection import async_session
from bot.services.clients import create_client, get_clients
from bot.services.lead_sources import get_lead_sources
from bot.services.leads import create_lead, get_leads
from bot.keyboards.leads import (
    get_leads_menu,
    get_lead_cancel_keyboard,
    get_lead_clients_keyboard,
    get_lead_sources_keyboard,
    get_lead_skip_keyboard,
)
from bot.states.leads import LeadForm


router = Router()


@router.message(F.text == "📥 Заявки")
async def leads_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Раздел заявок. Что будем делать?",
        reply_markup=get_leads_menu(),
    )


@router.message(F.text == "➕ Новая заявка")
async def start_lead(message: Message, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        clients = await get_clients(session)

    await state.set_state(LeadForm.client)

    await message.answer(
        "Выбери существующего ученика или создай нового:",
        reply_markup=get_lead_clients_keyboard(clients),
    )


@router.message(LeadForm.client, F.text == "❌ Отмена")
@router.message(LeadForm.new_client_nickname, F.text == "❌ Отмена")
@router.message(LeadForm.new_client_contact, F.text == "❌ Отмена")
@router.message(LeadForm.source, F.text == "❌ Отмена")
@router.message(LeadForm.subject, F.text == "❌ Отмена")
@router.message(LeadForm.notes, F.text == "❌ Отмена")
async def cancel_lead(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Создание заявки отменено.",
        reply_markup=get_leads_menu(),
    )


@router.message(LeadForm.client, F.text == "➕ Создать ученика")
async def start_new_client(message: Message, state: FSMContext):
    await state.set_state(LeadForm.new_client_nickname)
    await message.answer(
        "Введи имя или никнейм ученика:",
        reply_markup=get_lead_cancel_keyboard(),
    )


@router.message(LeadForm.client)
async def select_client(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Выбери ученика кнопкой или создай нового.")
        return

    try:
        client_id = int(message.text.split("|")[0].replace("👤", "").strip())
    except ValueError:
        await message.answer("Не удалось распознать ученика. Выбери его кнопкой.")
        return

    async with async_session() as session:
        clients = await get_clients(session)
        client = next((item for item in clients if item.id == client_id), None)

    if not client:
        await message.answer("Ученик не найден. Выбери другого.")
        return

    await state.update_data(client_id=client.id)
    await ask_source(message, state)


@router.message(LeadForm.new_client_nickname)
async def enter_client_nickname(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()

    if not nickname:
        await message.answer("Имя не может быть пустым.")
        return

    await state.update_data(new_client_nickname=nickname)
    await state.set_state(LeadForm.new_client_contact)

    await message.answer(
        "Введи контакт ученика или пропусти этот шаг:",
        reply_markup=get_lead_skip_keyboard(),
    )


@router.message(LeadForm.new_client_contact, F.text == "⏭ Пропустить")
@router.message(LeadForm.new_client_contact)
async def enter_client_contact(message: Message, state: FSMContext):
    contact = None if message.text == "⏭ Пропустить" else (message.text or "").strip()

    data = await state.get_data()

    async with async_session() as session:
        try:
            client = await create_client(
                session,
                nickname=data["new_client_nickname"],
                contact=contact,
            )
        except ValueError as error:
            await message.answer(str(error))
            return

    await state.update_data(client_id=client.id)
    await ask_source(message, state)


async def ask_source(message: Message, state: FSMContext):
    async with async_session() as session:
        sources = await get_lead_sources(session)

    if not sources:
        await state.clear()
        await message.answer(
            "Нет активных источников. Сначала добавь источник в разделе «📣 Источники».",
            reply_markup=get_leads_menu(),
        )
        return

    await state.set_state(LeadForm.source)
    await message.answer(
        "Выбери источник заявки:",
        reply_markup=get_lead_sources_keyboard(sources),
    )


@router.message(LeadForm.source)
async def select_source(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Выбери источник кнопкой.")
        return

    try:
        source_id = int(message.text.split("|")[0].replace("📣", "").strip())
    except ValueError:
        await message.answer("Выбери источник из списка кнопками.")
        return

    async with async_session() as session:
        sources = await get_lead_sources(session)
        source = next((item for item in sources if item.id == source_id), None)

    if not source:
        await message.answer("Источник не найден. Выбери другой.")
        return

    await state.update_data(source_id=source.id)
    await state.set_state(LeadForm.subject)

    await message.answer(
        "Укажи предмет заявки или пропусти:",
        reply_markup=get_lead_skip_keyboard(),
    )


@router.message(LeadForm.subject, F.text == "⏭ Пропустить")
@router.message(LeadForm.subject)
async def enter_subject(message: Message, state: FSMContext):
    subject = None if message.text == "⏭ Пропустить" else (message.text or "").strip()

    await state.update_data(subject=subject)
    await state.set_state(LeadForm.notes)

    await message.answer(
        "Добавь комментарий к заявке или пропусти:",
        reply_markup=get_lead_skip_keyboard(),
    )


@router.message(LeadForm.notes, F.text == "⏭ Пропустить")
@router.message(LeadForm.notes)
async def enter_notes(message: Message, state: FSMContext):
    notes = None if message.text == "⏭ Пропустить" else (message.text or "").strip()
    data = await state.get_data()

    async with async_session() as session:
        lead = await create_lead(
            session,
            client_id=data["client_id"],
            source_id=data["source_id"],
            subject=data.get("subject"),
            notes=notes,
        )

    await state.clear()

    await message.answer(
        f"✅ Заявка №{lead.id} создана!\n"
        f"Ученик ID: {lead.client_id}\n"
        f"Статус: Новая",
        reply_markup=get_leads_menu(),
    )


@router.message(F.text == "📋 Список заявок")
async def show_leads(message: Message, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        leads = await get_leads(session)

    if not leads:
        await message.answer("Заявок пока нет.", reply_markup=get_leads_menu())
        return

    lines = ["📋 <b>Последние заявки:</b>\n"]

    for lead in leads[:30]:
        lines.append(
            f"№{lead.id} | Ученик ID: {lead.client_id}\n"
            f"Предмет: {escape(lead.subject or 'Не указан')}\n"
            f"Статус: {escape(lead.status)}\n"
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_leads_menu(),
    )


@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    from bot.keyboards.main_menu import get_main_menu

    await message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(),
    )
