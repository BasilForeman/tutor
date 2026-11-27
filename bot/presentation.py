from decimal import Decimal


def person_label(name: str | None, contact: str | None = None) -> str:
    name = (name or "Не указано").strip()
    contact = (contact or "").strip()
    if contact and contact.casefold() != name.casefold():
        return f"{name} ({contact})"
    return name


def commission_mode_label(row) -> str:
    mode = row["commission_mode"]
    if mode == "rate_multiplier":
        return f"{row['commission_multiplier']} × ставка {row['rate']} ₽"
    if mode == "percent":
        return f"{row['commission_percentage']}% от платного заработка"
    if mode == "subscription":
        return f"абонемент {format_amount(row.get('agreed_commission'))} ₽, покупка {row['subscription_purchase_date'] or 'дата не указана'}"
    if mode == "fixed":
        return f"фиксированная сумма {format_amount(row.get('agreed_commission'))} ₽"
    return f"вручную {format_amount(row.get('agreed_commission'))} ₽"


def format_amount(value) -> str:
    amount = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    return f"{amount:.2f}"
