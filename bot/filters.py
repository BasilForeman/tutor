import os
from aiogram.types import Message


async def is_admin(message: Message) -> bool:
    admin_ids = {
        int(user_id.strip())
        for user_id in os.getenv("ADMIN_ID", "").split(",")
        if user_id.strip().isdigit()
    }

    return (
        message.from_user is not None
        and message.from_user.id in admin_ids
    )