import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import BaseMonitorModel

MonitorModel = BaseMonitorModel | HeartbeatMonitorModel
ERROR_BACKOFF_SECONDS = 15

logger = logging.getLogger("orion.uptime.worker")


class MonitorWorker:
    def __init__(self, monitor: MonitorModel, monitor_service: MonitorManager):
        self.monitor = monitor
        self.monitor_service = monitor_service

        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False

        if self._task:
            self._task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        if isinstance(self.monitor, HeartbeatMonitorModel):
            await self._run_heartbeat()
            return

        while self._running:
            start = asyncio.get_running_loop().time()
            try:
                monitor = await self.monitor_service.get_monitor(self.monitor.persisted_id, self.monitor.monitor_type)
                if monitor is None:
                    break

                self.monitor = monitor
                await self.monitor_service.check_and_update(self.monitor)
            except asyncio.CancelledError:
                break

            except Exception:
                logger.exception("Monitor %s check cycle failed.", self.monitor.id)

            elapsed = asyncio.get_running_loop().time() - start
            interval = self.monitor.expected_heartbeat_interval if isinstance(self.monitor, HeartbeatMonitorModel) else self.monitor.check_interval
            sleep_time = max(0, interval - elapsed)
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break

        self._running = False

    async def _run_heartbeat(self) -> None:
        while self._running:
            try:
                monitor = await self.monitor_service.get_monitor(self.monitor.persisted_id, self.monitor.monitor_type)
                if monitor is None:
                    break

                if not isinstance(monitor, HeartbeatMonitorModel):
                    break

                if monitor.last_heartbeat_at is None:
                    break

                self.monitor = monitor
                sleep_seconds = self._seconds_until_heartbeat_deadline(monitor)
                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)
                    continue

                await self.monitor_service.check_and_update(monitor)
                await asyncio.sleep(monitor.expected_heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Heartbeat monitor %s check cycle failed.", self.monitor.id)
                try:
                    await asyncio.sleep(ERROR_BACKOFF_SECONDS)
                except asyncio.CancelledError:
                    break
        self._running = False

    @staticmethod
    def _seconds_until_heartbeat_deadline(monitor: HeartbeatMonitorModel) -> float:
        if monitor.last_heartbeat_at is None:
            raise ValueError("A heartbeat deadline is unavailable before the first heartbeat.")
        deadline = monitor.last_heartbeat_at + timedelta(seconds=monitor.expected_heartbeat_interval + monitor.grace_period)
        return max(0.0, (deadline - datetime.now(UTC)).total_seconds())
