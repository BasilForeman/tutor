
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_clients_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить ученика")],
            [KeyboardButton(text="📋 Список учеников")],
            [KeyboardButton(text="🗄 Архивные ученики")],
            [KeyboardButton(text="🔎 Поиск / карточка ученика")],
            [KeyboardButton(text="✏️ Изменить ученика")],
            [KeyboardButton(text="📦 Архивировать ученика")],
            [KeyboardButton(text="⬅️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def get_clients_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def get_clients_skip_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )
