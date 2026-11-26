
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.database.connection import async_session
from bot.services.lead_sources import (
    create_lead_source,
    get_lead_sources,
)
from bot.keyboards.lead_sources import (
    get_lead_sources_menu,
    get_lead_sources_cancel_keyboard,
)
from bot.keyboards.main_menu import get_main_menu


router = Router()


class LeadSourceForm(StatesGroup):
    name = State()


@router.message(F.text == "📣 Источники")
async def lead_sources_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "📣 Управление источниками\n\nВыбери действие:",
        reply_markup=get_lead_sources_menu(),
    )


@router.message(LeadSourceForm.name, F.text == "❌ Отмена")
async def cancel_source_creation(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await message.answer(
        "Создание источника отменено.",
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
async def show_lead_sources(message: Message):
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
