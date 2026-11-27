import os
from aiogram.types import Message


def get_admin_ids() -> set[int]:
    admin_ids = set()
    for value in os.getenv("ADMIN_ID", "").split(","):
        try:
            parsed = int(value.strip())
        except ValueError:
            continue
        if parsed > 0:
            admin_ids.add(parsed)
    return admin_ids


async def is_admin(message: Message) -> bool:
    return (
        message.from_user is not None
        and message.from_user.id in get_admin_ids()
    )
