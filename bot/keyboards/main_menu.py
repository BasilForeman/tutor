from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():
    keyboard = [
        [
            KeyboardButton(text="👨‍🏫 Репетиторы"),
            KeyboardButton(text="👨‍🎓 Ученики"),
        ],
        [
            KeyboardButton(text="➕ Новая передача"),
            KeyboardButton(text="💰 Финансы"),
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )