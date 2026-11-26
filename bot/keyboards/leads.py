
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_leads_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая заявка")],
            [KeyboardButton(text="📋 Список заявок")],
            [KeyboardButton(text="⬅️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def get_lead_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def get_lead_clients_keyboard(clients):
    keyboard = [
        [KeyboardButton(text=f"👤 {client.id} | {client.nickname}")]
        for client in clients
    ]

    keyboard.append([KeyboardButton(text="➕ Создать ученика")])
    keyboard.append([KeyboardButton(text="❌ Отмена")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def get_lead_sources_keyboard(sources):
    keyboard = [
        [KeyboardButton(text=f"📣 {source.id} | {source.name}")]
        for source in sources
    ]

    keyboard.append([KeyboardButton(text="❌ Отмена")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def get_lead_skip_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )
