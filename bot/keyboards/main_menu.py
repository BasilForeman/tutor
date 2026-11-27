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
            KeyboardButton(text="⚖️ Корректировка комиссии"),
            KeyboardButton(text="↩️ Возврат платежа"),
        ],
        [
            KeyboardButton(text="📣 Источники"),
            KeyboardButton(text="📥 Заявки"),
        ],
        [KeyboardButton(text="📊 Синхронизировать Sheets")],
        [KeyboardButton(text="📈 Аналитика")],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
