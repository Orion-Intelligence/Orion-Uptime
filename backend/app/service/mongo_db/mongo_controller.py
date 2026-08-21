import os
from datetime import UTC

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

from app.service.constants import Collections


class DatabaseManager:
    def __init__(self):
        self._engine: AIOEngine | None = None

    @property
    def engine(self) -> AIOEngine:
        if self._engine is None:
            raise RuntimeError("MongoDB AIOEngine has not been initialized.")
        return self._engine

    async def connect(self) -> None:
        load_dotenv()
        mongo_uri = os.environ["MONGO_URI"]
        database_name = os.environ["DATABASE_NAME"]
        client = AsyncIOMotorClient(mongo_uri, tz_aware=True, tzinfo=UTC)
        self._engine = AIOEngine(client=client, database=database_name)
        await self.engine.client.admin.command("ping")
        await self._create_indexes()

    async def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.client.close()
            self._engine = None

    async def _create_indexes(self) -> None:
        await self._create_monitor_result_indexes()
        await self._create_incident_indexes()
        await self._create_heartbeat_indexes()
        await self._create_status_page_indexes()

    async def _create_monitor_result_indexes(self) -> None:
        collection = self.engine.database[Collections.MONITOR_RESULTS]
        await collection.create_index([("monitor_id", ASCENDING)])
        await collection.create_index([("checked_at", DESCENDING)])
        await collection.create_index([("monitor_id", ASCENDING), ("checked_at", DESCENDING)])
        await collection.create_index([("monitor_id", ASCENDING), ("is_slow", ASCENDING)])
        await collection.create_index([("monitor_id", ASCENDING), ("success", ASCENDING)])
        retention_seconds = int(os.environ.get("MONITOR_RESULT_RETENTION_DAYS", "180")) * 24 * 60 * 60
        try:
            await collection.create_index([("checked_at", ASCENDING)], name="monitor_results_ttl", expireAfterSeconds=retention_seconds)
        except OperationFailure:
            await collection.drop_index("monitor_results_ttl")
            await collection.create_index([("checked_at", ASCENDING)], name="monitor_results_ttl", expireAfterSeconds=retention_seconds)

    async def _create_incident_indexes(self) -> None:
        collection = self.engine.database[Collections.INCIDENTS]
        await collection.create_index([("monitor_id", ASCENDING), ("resolved_at", ASCENDING)])
        await collection.create_index([("monitor_id", ASCENDING), ("monitor_type", ASCENDING), ("resolved_at", ASCENDING)])
        await collection.create_index([("started_at", DESCENDING)])
        await collection.create_index([("is_resolved", ASCENDING)])

    async def _create_heartbeat_indexes(self) -> None:
        collection = self.engine.database[Collections.HEARTBEAT_MONITORS]
        await collection.create_index("heartbeat_token_hash", unique=True)
        await collection.create_index("is_active")
        await collection.create_index("name")

    async def _create_status_page_indexes(self) -> None:
        collection = self.engine.database[Collections.STATUS_PAGES]
        await collection.create_index("slug", unique=True)
        await collection.create_index("created_at")

    def get_engine(self) -> AIOEngine:
        return self.engine

db_manager = DatabaseManager()

async def get_engine() -> AIOEngine:
    return db_manager.get_engine()
