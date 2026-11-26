from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():
    keyboard = [
        [
            KeyboardButton(text="👨‍🏫 Репетиторы"),
            KeyboardButton(text="👨‍🎓 Ученики"),
        ],
        [
            KeyboardButton(text="➕ Новая передача"),
            KeyboardButton(text="📋 Список передач"),
        ],
        [
            KeyboardButton(text="🔚 Завершить обучение"),
        ],
        [
            KeyboardButton(text="📚 Учёт занятий"),
            KeyboardButton(text="💰 Финансы"),
            KeyboardButton(text="💵 Записать платёж"),
        ],
        [
            KeyboardButton(text="📣 Источники"),
            KeyboardButton(text="📥 Заявки"),
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )