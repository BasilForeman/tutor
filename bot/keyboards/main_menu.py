from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():
    keyboard = [
        [KeyboardButton(text="➕ Новая передача")],
        [KeyboardButton(text="📚 Занятия"), KeyboardButton(text="💰 Выплаты")],
        [KeyboardButton(text="👥 Репетиторы"), KeyboardButton(text="📊 Статистика")],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )


def _section_menu(*rows):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=value) for value in row] for row in rows],
        resize_keyboard=True,
    )


def get_transfers_menu():
    return _section_menu(
        ("➕ Оформить передачу",),
        ("📋 Список передач", "🔚 Завершить обучение"),
        ("⬅️ Главное меню",),
    )


def get_lessons_menu():
    return _section_menu(("➕ Записать занятие",), ("⬅️ Главное меню",))


def get_payouts_menu():
    return _section_menu(
        ("📋 Текущие долги", "💵 Записать платёж"),
        ("🧾 История платежей",),
        ("⚖️ Корректировка комиссии", "↩️ Возврат платежа"),
        ("⬅️ Главное меню",),
    )


def get_records_menu():
    return _section_menu(
        ("➕ Добавить репетитора", "📋 Список репетиторов"),
        ("🔎 Поиск / карточка репетитора", "🗄 Архивные репетиторы"),
        ("✏️ Изменить репетитора", "📦 Архивировать репетитора"),
        ("👨‍🎓 Ученики", "📣 Источники"),
        ("📥 Заявки",),
        ("⬅️ Главное меню",),
    )


def get_statistics_menu():
    return _section_menu(
        ("📅 Сегодня", "📅 7 дней"),
        ("📅 Этот месяц", "📅 Прошлый месяц"),
        ("📊 Синхронизировать Sheets",),
        ("⬅️ Главное меню",),
    )
