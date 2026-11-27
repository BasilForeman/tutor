
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_lead_sources_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить источник")],
            [KeyboardButton(text="📋 Список источников")],
            [KeyboardButton(text="🗄 Архивные источники")],
            [KeyboardButton(text="🔎 Поиск / карточка источника")],
            [KeyboardButton(text="✏️ Изменить источник")],
            [KeyboardButton(text="📦 Архивировать источник")],
            [KeyboardButton(text="⬅️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def get_lead_sources_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )
