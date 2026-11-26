from aiogram.types import Message
import os


async def is_admin(message: Message) -> bool:
    admin_id = int(os.getenv("ADMIN_ID", "0"))

    return (
        message.from_user is not None
        and message.from_user.id == admin_id
    )