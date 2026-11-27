from copy import deepcopy
from typing import Any, Dict, Mapping, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func

from bot.database.connection import async_session
from bot.database.models import FSMState


class PostgresFSMStorage(BaseStorage):
    """Small PostgreSQL-backed aiogram storage using the project's async engine."""

    @staticmethod
    def _key(key: StorageKey) -> dict[str, Any]:
        return {
            "bot_id": key.bot_id,
            "chat_id": key.chat_id,
            "user_id": key.user_id,
            "thread_id": key.thread_id or 0,
            "business_connection_id": key.business_connection_id or "",
            "destiny": key.destiny,
        }

    async def set_state(self, key: StorageKey, state: Optional[str | State] = None) -> None:
        value = state.state if isinstance(state, State) else state
        keys = self._key(key)
        async with async_session() as session:
            statement = insert(FSMState).values(**keys, state=value, data={})
            statement = statement.on_conflict_do_update(
                index_elements=[
                    FSMState.bot_id, FSMState.chat_id, FSMState.user_id,
                    FSMState.thread_id, FSMState.business_connection_id, FSMState.destiny,
                ],
                set_={"state": value, "updated_at": func.current_timestamp()},
            )
            await session.execute(statement)
            await session.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        keys = self._key(key)
        async with async_session() as session:
            row = await session.get(FSMState, tuple(keys.values()))
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        keys = self._key(key)
        payload = deepcopy(dict(data))
        async with async_session() as session:
            statement = insert(FSMState).values(**keys, state=None, data=payload)
            statement = statement.on_conflict_do_update(
                index_elements=[
                    FSMState.bot_id, FSMState.chat_id, FSMState.user_id,
                    FSMState.thread_id, FSMState.business_connection_id, FSMState.destiny,
                ],
                set_={"data": payload, "updated_at": func.current_timestamp()},
            )
            await session.execute(statement)
            await session.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        keys = self._key(key)
        async with async_session() as session:
            row = await session.get(FSMState, tuple(keys.values()))
            return deepcopy(row.data) if row and row.data else {}

    async def close(self) -> None:
        # The engine is shared with the application's repositories.
        return None
