import asyncio
import contextlib
import logging
import time
from collections.abc import Callable

from app.modules.monitoring_controller.monitoring_controller import MonitorManager
from app.modules.monitoring_controller.worker import MonitorWorker
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorType

RECONCILE_INTERVAL_SECONDS = 30
SCHEDULER_STALL_SECONDS = 180

logger = logging.getLogger("orion.uptime.scheduler")


class MonitorScheduler:
    def __init__(self, monitor_service: MonitorManager, reconcile_interval: float = RECONCILE_INTERVAL_SECONDS, on_fatal: Callable[[BaseException], None] | None = None, clock: Callable[[], float] = time.monotonic):
        self.monitor_service = monitor_service
        self.reconcile_interval = reconcile_interval
        self.on_fatal = on_fatal
        self.clock = clock
        self._running = False
        self._workers: dict[str, MonitorWorker] = {}
        self._reconcile_task: asyncio.Task | None = None
        self.last_reconcile_at: float | None = None
        self.last_reconcile_error: str | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            await self.reconcile()
        except Exception:
            logger.exception("Initial monitor reconciliation failed; retrying on the next cycle.")
        task = asyncio.create_task(self._reconcile_loop())
        task.add_done_callback(self._handle_loop_exit)
        self._reconcile_task = task

    async def reconcile(self) -> None:
        try:
            monitors = await self.monitor_service.list_active_monitors()
            expected_ids: set[str] = set()
            for monitor in monitors:
                if monitor.monitor_type == MonitorType.HEARTBEAT and monitor.last_heartbeat_at is None:
                    continue
                expected_ids.add(monitor.persisted_id)
                worker = self._workers.get(monitor.persisted_id)
                if worker is not None and not worker.is_alive:
                    logger.warning("Monitor worker %s stopped unexpectedly; restarting it.", monitor.persisted_id)
                    await self.stop_worker(monitor.persisted_id)
                await self.start_worker(monitor)
            for monitor_id in [monitor_id for monitor_id in self._workers if monitor_id not in expected_ids]:
                await self.stop_worker(monitor_id)
        except Exception as exc:
            self.last_reconcile_error = f"{type(exc).__name__}: {exc}"
            raise
        self.last_reconcile_at = self.clock()
        self.last_reconcile_error = None

    async def start_worker(self, monitor) -> None:
        if monitor.monitor_type == MonitorType.HEARTBEAT and monitor.last_heartbeat_at is None:
            return

        existing = self._workers.get(monitor.persisted_id)
        if existing is not None:
            if existing.is_alive:
                return
            await self.stop_worker(monitor.persisted_id)

        worker = MonitorWorker(
            monitor=monitor,
            monitor_service=self.monitor_service,
        )

        self._workers[monitor.persisted_id] = worker
        await worker.start()

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconcile_task
            self._reconcile_task = None
        worker_ids = list(self._workers.keys())
        for monitor_id in worker_ids:
            await self.stop_worker(monitor_id)

    async def stop_worker(self, monitor_id: str) -> None:
        worker = self._workers.pop(monitor_id, None)

        if worker is None:
            return

        await worker.stop()

    def is_healthy(self, stall_seconds: float = SCHEDULER_STALL_SECONDS) -> bool:
        if not self._running or self.last_reconcile_at is None:
            return False
        return self.clock() - self.last_reconcile_at <= stall_seconds

    def status(self) -> dict:
        alive = sum(1 for worker in self._workers.values() if worker.is_alive)
        return {
            "running": self._running,
            "workers": len(self._workers),
            "alive_workers": alive,
            "seconds_since_reconcile": None if self.last_reconcile_at is None else round(self.clock() - self.last_reconcile_at, 1),
            "last_reconcile_error": self.last_reconcile_error,
        }

    async def _reconcile_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.reconcile_interval)
            if not self._running:
                break
            try:
                await self.reconcile()
            except Exception:
                logger.exception("Monitor reconciliation failed; retrying on the next cycle.")

    def _handle_loop_exit(self, task: asyncio.Task) -> None:
        if task.cancelled() or not self._running:
            return
        exc = task.exception()
        if exc is None:
            return
        logger.critical("Monitor reconciliation loop died: %r", exc)
        if self.on_fatal is not None:
            self.on_fatal(exc)

scheduler: MonitorScheduler | None = None
