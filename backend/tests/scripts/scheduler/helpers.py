from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from orion.management.jobs.monitoring_controller.scheduler import MonitorScheduler
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType

NOW = datetime.now(UTC)


def _returns(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


async def _noop(*_args, **_kwargs):
    return None


def _monitor_service(active):
    holder = {"active": active}

    async def list_active_monitors():
        value = holder["active"]
        if isinstance(value, Exception):
            raise value
        return value

    service = SimpleNamespace(
        list_active_monitors=list_active_monitors,
        monitor_result_service=SimpleNamespace(seed_history=_noop),
        get_monitor=_returns(None),
        check_and_update=_noop,
    )
    return service, holder


def _monitor(monitor_id):
    return SimpleNamespace(persisted_id=monitor_id, monitor_type=MonitorType.HTTP)


def _scheduler(active=None, clock=None):
    service, holder = _monitor_service(active if active is not None else [])
    scheduler = MonitorScheduler(service, reconcile_interval=3600, clock=clock or (lambda: 0.0))
    return scheduler, holder
