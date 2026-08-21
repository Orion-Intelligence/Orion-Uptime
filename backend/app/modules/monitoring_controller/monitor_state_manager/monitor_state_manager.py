from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv
from odmantic import AIOEngine

from app.service.constants import Collections
from app.service.mongo_db.shared_models.db_monitor_state_model import MonitorStateModel, MonitorStateResult, MonitorTransition
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus, MonitorType


class MonitorStateManager:
    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.MONITOR_STATES]

    async def get_or_create(self, monitor_id: str, monitor_type: MonitorType) -> MonitorStateModel:
        document = await self.collection.find_one(
            {"monitor_id": monitor_id, "monitor_type": monitor_type}
        )
        if document is None:
            state = MonitorStateModel(
                monitor_id=monitor_id,
                monitor_type=monitor_type,
            )
            await self.collection.insert_one(state.model_dump())
            return state

        return MonitorStateModel.model_validate(document)

    async def process_result(self, monitor_id: str, monitor_type: MonitorType, success: bool, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> MonitorStateResult:
        state = await self.get_or_create(monitor_id, monitor_type)
        previous_status = state.status

        load_dotenv()
        recovery_threshold = int(os.environ["MONITOR_RECOVERY_THRESHOLD"])
        failure_threshold = int(os.environ["MONITOR_FAILURE_THRESHOLD"])

        if success:
            state.consecutive_successes += 1
            state.consecutive_failures = 0
            if previous_status == MonitorStatus.UNKNOWN or previous_status == MonitorStatus.DOWN and state.consecutive_successes >= recovery_threshold:
                state.status = MonitorStatus.UP
        else:
            state.consecutive_failures += 1
            state.consecutive_successes = 0
            if previous_status != MonitorStatus.DOWN and state.consecutive_failures >= failure_threshold:
                state.status = MonitorStatus.DOWN

        state.last_checked_at = checked_at
        state.last_status_code = status_code
        state.last_response_time_ms = response_time_ms

        await self.collection.update_one(
            {
                "monitor_id": state.monitor_id,
                "monitor_type": state.monitor_type,
            },
            {
                "$set": {
                    "status": state.status,
                    "consecutive_failures": state.consecutive_failures,
                    "consecutive_successes": state.consecutive_successes,
                    "last_checked_at": state.last_checked_at,
                    "last_status_code": state.last_status_code,
                    "last_response_time_ms": state.last_response_time_ms,
                }
            },
        )

        transition = MonitorTransition.NONE
        if previous_status != state.status:
            if state.status == MonitorStatus.DOWN:
                transition = MonitorTransition.DOWN
            elif state.status == MonitorStatus.UP:
                transition = MonitorTransition.UP

        return MonitorStateResult(
            state=state,
            previous_status=previous_status,
            current_status=state.status,
            transition=transition,
        )

    async def delete_for_monitor(self, monitor_id: str) -> None:
        await self.collection.delete_many({"monitor_id": monitor_id})
