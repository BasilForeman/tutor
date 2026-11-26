import asyncio

from dotenv import load_dotenv
from bot.integrations.google_sheets import sync_all


async def main():
    load_dotenv()

    try:
        await sync_all()
        print("Google Sheets успешно синхронизированы!")
    except Exception as error:
        print(f"Ошибка синхронизации: {error}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
