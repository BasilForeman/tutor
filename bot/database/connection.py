import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker
)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден в .env")

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True
)

async_session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)


async def check_connection():
    from sqlalchemy import text

    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))
        return result.scalar_one()