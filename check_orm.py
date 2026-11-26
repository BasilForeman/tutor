import asyncio

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from bot.database.connection import async_session, check_connection
from bot.database.models import (
    Tutor,
    Client,
    LeadSource,
    Assignment,
    Payment,
)


async def main():
    print("1. Checking PostgreSQL connection...")
    result = await check_connection()
    print(f"   Connection OK: {result}")

    async with async_session() as session:
        print("\n2. Checking tables...")

        for model in (Tutor, Client, LeadSource, Assignment, Payment):
            result = await session.execute(
                select(model.id).limit(1)
            )
            result.first()
            print(f"   {model.__tablename__}: OK")

        print("\n3. Checking ORM relationships...")

        result = await session.execute(
            select(Assignment)
            .options(
                selectinload(Assignment.tutor),
                selectinload(Assignment.client),
                selectinload(Assignment.source),
                selectinload(Assignment.payments),
            )
            .limit(5)
        )

        assignments = result.scalars().all()

        print(f"   Assignments loaded: {len(assignments)}")

        for assignment in assignments:
            print(
                f"   Assignment #{assignment.id}: "
                f"tutor={assignment.tutor.nickname}, "
                f"client={assignment.client.nickname}, "
                f"payments={len(assignment.payments)}"
            )

        print("\n4. Checking financial VIEW...")

        result = await session.execute(
            text("""
                SELECT assignment_id,
                       commission_amount,
                       paid_amount,
                       remaining_amount
                FROM assignment_finances
                LIMIT 5
            """)
        )

        rows = result.fetchall()

        print(f"   VIEW accessible: OK")
        print(f"   Rows loaded: {len(rows)}")

        for row in rows:
            print(f"   {row}")

    print("\nAll checks completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
