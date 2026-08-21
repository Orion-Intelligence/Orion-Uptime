from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from odmantic import AIOEngine

from app.service.constants import Collections
from app.service.mongo_db.documents import with_string_id
from app.service.mongo_db.shared_models.db_monitor_result_model import MonitorResultModel
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus, MonitorType


class MonitorResultManager:
    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.MONITOR_RESULTS]

    async def record_result(self, monitor_id: str, monitor_type: MonitorType, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, success: bool, is_slow: bool = False) -> MonitorResultModel:
        result = MonitorResultModel(
            monitor_id=monitor_id,
            monitor_type=monitor_type,
            status=status,
            status_code=status_code,
            response_time_ms=response_time_ms,
            success=success,
            is_slow=is_slow,
            checked_at=datetime.now(UTC),
        )
        document = result.model_dump()
        document.pop("id", None)
        inserted = await self.collection.insert_one(document)
        result.id = str(inserted.inserted_id)
        return result

    async def seed_history(self, monitor_id: str, monitor_type: MonitorType, days: int = 45) -> None:
        if await self.collection.count_documents({"monitor_id": monitor_id}, limit=1):
            return
        now = datetime.now(UTC)
        await self.collection.insert_many(
            [
                MonitorResultModel(
                    monitor_id=monitor_id,
                    monitor_type=monitor_type,
                    status=MonitorStatus.UP,
                    status_code=None,
                    response_time_ms=None,
                    success=True,
                    is_slow=False,
                    checked_at=now - timedelta(days=offset),
                ).model_dump(exclude={"id"})
                for offset in range(1, days + 1)
            ]
        )

    async def average_response_time(self) -> float:
        pipeline = [
            {"$match": {"response_time_ms": {"$ne": None}}},
            {"$group": {"_id": None, "avg": {"$avg": "$response_time_ms"}}},
        ]
        result = await self.collection.aggregate(pipeline).to_list(1)
        if not result:
            return 0.0
        return round(result[0]["avg"], 2)

    async def get_first_check_times(self, monitor_ids: list[str]) -> dict[str, datetime]:
        if not monitor_ids:
            return {}
        pipeline = [
            {
                "$match": {
                    "monitor_id": {"$in": monitor_ids},
                    "status": {"$ne": MonitorStatus.UNKNOWN},
                }
            },
            {"$group": {"_id": "$monitor_id", "checked_at": {"$min": "$checked_at"}}},
        ]
        results = await self.collection.aggregate(pipeline).to_list(None)
        return {result["_id"]: result["checked_at"] for result in results}

    async def get_recent(self, limit: int = 20) -> list[MonitorResultModel]:
        cursor = self.collection.find().sort("checked_at", -1).limit(limit)
        results = []
        async for document in cursor:
            results.append(MonitorResultModel(**with_string_id(document)))
        return results

    async def get_response_history(self, monitor_id: str, days: int = 7) -> list[MonitorResultModel]:
        start_date = datetime.now(UTC) - timedelta(days=days)
        cursor = self.collection.find(
            {
                "monitor_id": monitor_id,
                "checked_at": {"$gte": start_date},
            }
        ).sort("checked_at", 1)
        results = []
        async for document in cursor:
            results.append(MonitorResultModel(**with_string_id(document)))
        return results

    async def get_status_history(self, monitor_id: str, days: int = 7) -> list[MonitorResultModel]:
        return await self.get_response_history(monitor_id, days)

    async def get_statistics(self, monitor_id: str, days: int = 7) -> dict[str, int]:
        start_date = datetime.now(UTC) - timedelta(days=days)
        pipeline = [
            {
                "$match": {
                    "monitor_id": monitor_id,
                    "checked_at": {"$gte": start_date},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "successful": {"$sum": {"$cond": ["$success", 1, 0]}},
                }
            },
        ]
        result = await self.collection.aggregate(pipeline).to_list(1)
        if not result:
            return {"total": 0, "successful": 0}
        return {
            "total": result[0]["total"],
            "successful": result[0]["successful"],
        }

    async def get_public_uptime_breakdown(self, monitor_ids: list[str], now: datetime) -> dict[str, Any]:
        if not monitor_ids:
            return {
                "daily": [],
                "monitors_90": [],
                "overall_24": [],
                "overall_7": [],
                "overall_30": [],
                "overall_90": [],
            }

        start_90_days = now - timedelta(days=90)
        daily_start = datetime(
            now.year,
            now.month,
            now.day,
            tzinfo=UTC,
        ) - timedelta(days=89)
        pipeline = [
            {
                "$match": {
                    "monitor_id": {"$in": monitor_ids},
                    "checked_at": {"$gte": start_90_days},
                    "status": {"$ne": MonitorStatus.UNKNOWN},
                }
            },
            {
                "$facet": {
                    "daily": [
                        {
                            "$group": {
                                "_id": {
                                    "monitor_id": "$monitor_id",
                                    "date": {
                                        "$dateToString": {
                                            "format": "%Y-%m-%d",
                                            "date": "$checked_at",
                                            "timezone": "UTC",
                                        }
                                    },
                                },
                                "total": {"$sum": 1},
                                "successful": {
                                    "$sum": {"$cond": ["$success", 1, 0]}
                                },
                            }
                        }
                    ],
                    "monitors_90": [
                        {"$match": {"checked_at": {"$gte": daily_start}}},
                        {
                            "$group": {
                                "_id": "$monitor_id",
                                "total": {"$sum": 1},
                                "successful": {
                                    "$sum": {"$cond": ["$success", 1, 0]}
                                },
                            }
                        }
                    ],
                    "overall_24": self._uptime_window_pipeline(
                        now - timedelta(hours=24)
                    ),
                    "overall_7": self._uptime_window_pipeline(
                        now - timedelta(days=7)
                    ),
                    "overall_30": self._uptime_window_pipeline(
                        now - timedelta(days=30)
                    ),
                    "overall_90": self._uptime_window_pipeline(start_90_days),
                }
            },
        ]
        results = await self.collection.aggregate(pipeline).to_list(1)
        return results[0] if results else {}

    @staticmethod
    def _uptime_window_pipeline(started_at: datetime) -> list[dict[str, Any]]:
        return [
            {"$match": {"checked_at": {"$gte": started_at}}},
            {
                "$group": {
                    "_id": "$monitor_id",
                    "total": {"$sum": 1},
                    "successful": {"$sum": {"$cond": ["$success", 1, 0]}},
                }
            },
            {
                "$project": {
                    "uptime_percentage": {
                        "$multiply": [
                            {"$divide": ["$successful", "$total"]},
                            100,
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "uptime_percentage": {"$avg": "$uptime_percentage"},
                }
            },
        ]

    async def get_public_response_time(self, monitor_id: str, now: datetime) -> dict[str, Any]:
        pipeline = [
            {
                "$match": {
                    "monitor_id": monitor_id,
                    "checked_at": {"$gte": now - timedelta(hours=24)},
                    "response_time_ms": {"$ne": None},
                }
            },
            {
                "$facet": {
                    "points": [
                        {
                            "$group": {
                                "_id": {
                                    "$dateTrunc": {
                                        "date": "$checked_at",
                                        "unit": "minute",
                                        "binSize": 15,
                                        "timezone": "UTC",
                                    }
                                },
                                "response_time_ms": {"$avg": "$response_time_ms"},
                            }
                        },
                        {"$sort": {"_id": 1}},
                    ],
                    "metrics": [
                        {
                            "$group": {
                                "_id": None,
                                "average_ms": {"$avg": "$response_time_ms"},
                                "maximum_ms": {"$max": "$response_time_ms"},
                                "minimum_ms": {"$min": "$response_time_ms"},
                            }
                        }
                    ],
                }
            },
        ]
        results = await self.collection.aggregate(pipeline).to_list(1)
        return results[0] if results else {"points": [], "metrics": []}

    async def count_slow_checks(self, monitor_id: str) -> int:
        return await self.collection.count_documents(
            {"monitor_id": monitor_id, "is_slow": True}
        )

    async def delete_for_monitor(self, monitor_id: str) -> None:
        await self.collection.delete_many({"monitor_id": monitor_id})
