
from aiogram import Router, F
from aiogram.types import Message
from html import escape
from aiogram.fsm.context import FSMContext

from bot.database.connection import async_session
from bot.services.clients import create_client, get_clients
from bot.services.lead_sources import get_lead_sources
from bot.services.leads import (
    create_lead, get_leads, get_lead_by_id, get_lead_history,
    update_lead, update_lead_status,
)
from bot.services.clients import get_client_by_id
from bot.services.lead_sources import get_lead_source_by_id
from bot.keyboards.leads import (
    get_leads_menu,
    get_lead_cancel_keyboard,
    get_lead_clients_keyboard,
    get_lead_sources_keyboard,
    get_lead_skip_keyboard,
    get_lead_status_keyboard,
    get_lead_filter_keyboard,
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
@router.message(LeadForm.search, F.text == "❌ Отмена")
@router.message(LeadForm.edit_id, F.text == "❌ Отмена")
@router.message(LeadForm.edit_subject, F.text == "❌ Отмена")
@router.message(LeadForm.edit_notes, F.text == "❌ Отмена")
@router.message(LeadForm.status_id, F.text == "❌ Отмена")
@router.message(LeadForm.status, F.text == "❌ Отмена")
@router.message(LeadForm.lost_reason, F.text == "❌ Отмена")
@router.message(LeadForm.filter_status, F.text == "❌ Отмена")
async def cancel_lead(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие с заявкой отменено.",
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
            changed_by=str(message.from_user.id if message.from_user else "telegram"),
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


@router.message(F.text == "🔎 Найти / карточка заявки")
async def lead_search_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadForm.search)
    await message.answer("Введи ID, имя ученика, предмет или комментарий заявки:")


@router.message(LeadForm.search)
async def lead_search(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введи ID или поисковый текст.")
        return
    async with async_session() as session:
        if query.isdigit():
            lead = await get_lead_by_id(session, int(query))
            leads = [lead] if lead else []
        else:
            leads = await get_leads(session, active_only=None, search=query)
        cards = []
        for lead in leads[:20]:
            client = await get_client_by_id(session, lead.client_id)
            source = await get_lead_source_by_id(session, lead.source_id)
            history = await get_lead_history(session, lead.id)
            history_text = "\n".join(
                f"• {escape(event.old_status or '—')} → {escape(event.new_status)}"
                f" ({escape((event.reason or '').strip() or 'без причины')}; {escape(event.changed_by)})"
                for event in (history or [])[-8:]
            ) or "История пока пуста"
            cards.append(
                f"<b>Заявка #{lead.id}</b>\nУченик: {escape(client.nickname if client else 'Не найден')}\n"
                f"Источник: {escape(source.name if source else 'Не найден')}\nПредмет: {escape(lead.subject or 'Не указан')}\n"
                f"Статус: {escape(lead.status)}\nПричина потери: {escape(lead.lost_reason or '—')}\n"
                f"<b>История статусов:</b>\n{history_text}"
            )
    await state.clear()
    if not cards:
        await message.answer("Заявки не найдены.", reply_markup=get_leads_menu())
    else:
        await message.answer("\n\n".join(cards), parse_mode="HTML", reply_markup=get_leads_menu())


@router.message(F.text == "✏️ Изменить заявку")
async def lead_edit_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadForm.edit_id)
    await message.answer("Введи ID заявки для изменения предмета и комментария:")


@router.message(LeadForm.edit_id)
async def lead_edit_id(message: Message, state: FSMContext):
    try:
        lead_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        lead = await get_lead_by_id(session, lead_id)
    if not lead:
        await state.clear()
        await message.answer("Заявка не найдена.", reply_markup=get_leads_menu())
        return
    await state.update_data(lead_id=lead_id)
    await state.set_state(LeadForm.edit_subject)
    await message.answer("Введи новый предмет или «⏭ Пропустить», чтобы очистить:")


@router.message(LeadForm.edit_subject)
async def lead_edit_subject(message: Message, state: FSMContext):
    subject = (message.text or "").strip()
    if not subject:
        await message.answer("Введи предмет или «⏭ Пропустить».")
        return
    await state.update_data(subject="" if subject == "⏭ Пропустить" else subject)
    await state.set_state(LeadForm.edit_notes)
    await message.answer("Введи новый комментарий или «⏭ Пропустить», чтобы очистить:")


@router.message(LeadForm.edit_notes)
async def lead_edit_notes(message: Message, state: FSMContext):
    notes = (message.text or "").strip()
    if not notes:
        await message.answer("Введи комментарий или «⏭ Пропустить».")
        return
    data = await state.get_data()
    async with async_session() as session:
        lead = await update_lead(session, data["lead_id"], subject=data["subject"], notes="" if notes == "⏭ Пропустить" else notes)
    await state.clear()
    await message.answer(f"✅ Заявка #{lead.id} обновлена.", reply_markup=get_leads_menu())


@router.message(F.text == "🔄 Изменить статус заявки")
async def lead_status_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadForm.status_id)
    await message.answer("Введи ID заявки:")


@router.message(LeadForm.status_id)
async def lead_status_id(message: Message, state: FSMContext):
    try:
        lead_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужен числовой ID.")
        return
    async with async_session() as session:
        lead = await get_lead_by_id(session, lead_id)
    if not lead:
        await state.clear()
        await message.answer("Заявка не найдена.", reply_markup=get_leads_menu())
        return
    await state.update_data(lead_id=lead_id)
    await state.set_state(LeadForm.status)
    await message.answer(f"Текущий статус: {lead.status}. Выбери новый:", reply_markup=get_lead_status_keyboard())


@router.message(LeadForm.status)
async def lead_status_select(message: Message, state: FSMContext):
    statuses = {"🆕 Новая": "new", "🔄 В работе": "in_progress", "✅ Передана": "assigned", "❌ Потеряна": "lost"}
    status = statuses.get((message.text or "").strip())
    if not status:
        await message.answer("Выбери статус кнопкой.", reply_markup=get_lead_status_keyboard())
        return
    await state.update_data(status=status)
    if status == "lost":
        await state.set_state(LeadForm.lost_reason)
        await message.answer("Почему заявка потеряна? Укажи причину:", reply_markup=get_lead_cancel_keyboard())
        return
    data = await state.get_data()
    try:
        async with async_session() as session:
            lead = await update_lead_status(session, data["lead_id"], status, changed_by=str(message.from_user.id if message.from_user else "telegram"))
    except ValueError as error:
        await message.answer(str(error), reply_markup=get_leads_menu())
        await state.clear()
        return
    await state.clear()
    await message.answer(f"✅ Статус заявки #{lead.id}: {lead.status}", reply_markup=get_leads_menu())


@router.message(LeadForm.lost_reason)
async def lead_lost_reason(message: Message, state: FSMContext):
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина не может быть пустой.")
        return
    data = await state.get_data()
    try:
        async with async_session() as session:
            lead = await update_lead_status(session, data["lead_id"], "lost", lost_reason=reason,
                                            changed_by=str(message.from_user.id if message.from_user else "telegram"))
    except ValueError as error:
        await message.answer(str(error), reply_markup=get_leads_menu())
        await state.clear()
        return
    await state.clear()
    await message.answer(f"✅ Заявка #{lead.id} отмечена потерянной. Причина сохранена в истории.", reply_markup=get_leads_menu())


@router.message(F.text == "🔍 Фильтр заявок")
async def lead_filter_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LeadForm.filter_status)
    await message.answer("Выбери статус:", reply_markup=get_lead_filter_keyboard())


@router.message(LeadForm.filter_status)
async def lead_filter(message: Message, state: FSMContext):
    statuses = {"🆕 Новая": "new", "🔄 В работе": "in_progress", "✅ Передана": "assigned", "❌ Потеряна": "lost"}
    value = (message.text or "").strip()
    if value != "Все статусы" and value not in statuses:
        await message.answer("Выбери значение кнопкой.", reply_markup=get_lead_filter_keyboard())
        return
    async with async_session() as session:
        leads = await get_leads(session, status=statuses.get(value))
        cards = []
        for lead in leads[:30]:
            client = await get_client_by_id(session, lead.client_id)
            cards.append(f"#{lead.id} | {escape(client.nickname if client else 'Ученик не найден')} | {escape(lead.subject or 'Предмет не указан')} | {escape(lead.status)}")
    await state.clear()
    if not cards:
        await message.answer("Заявок с таким статусом нет.", reply_markup=get_leads_menu())
    else:
        await message.answer("<b>Результаты:</b>\n" + "\n".join(cards), parse_mode="HTML", reply_markup=get_leads_menu())
