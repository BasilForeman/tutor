from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_tutors_menu():
    keyboard = [
        [KeyboardButton(text="➕ Добавить репетитора")],
        [KeyboardButton(text="📋 Список репетиторов")],
        [KeyboardButton(text="⬅️ Главное меню")],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )


def get_subject_keyboard():
    keyboard = [
        [KeyboardButton(text="Пропустить предмет")],
        [KeyboardButton(text="❌ Отмена")],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
