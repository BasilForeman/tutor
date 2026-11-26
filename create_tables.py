import asyncio

from sqlalchemy import inspect

from bot.database.connection import engine
from bot.database.models import Base


async def main():
    try:
        async with engine.begin() as conn:
            def list_relations(sync_conn):
                inspector = inspect(sync_conn)
                relations = inspector.get_table_names() + inspector.get_view_names()
                get_materialized_views = getattr(
                    inspector, "get_materialized_view_names", None
                )
                if get_materialized_views:
                    relations += get_materialized_views()
                return relations

            existing = await conn.run_sync(list_relations)
            if existing:
                raise RuntimeError(
                    "База уже содержит таблицы или представления. "
                    "create_all не обновляет существующую схему; "
                    "проверьте и примените миграции вручную."
                )
            await conn.run_sync(Base.metadata.create_all)
        print("Таблицы успешно созданы в пустой базе!")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
