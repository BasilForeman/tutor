print("CHECK_DB FILE STARTED")

import asyncio

from bot.database.connection import check_connection, engine


async def main():
    print("MAIN STARTED")

    try:
        result = await check_connection()
        print(f"PostgreSQL connected! Result: {result}")
    except Exception as error:
        print(f"Database connection error: {error}")
    finally:
        await engine.dispose()
        print("CONNECTION CLOSED")


if __name__ == "__main__":
    print("RUNNING AS MAIN")
    asyncio.run(main())