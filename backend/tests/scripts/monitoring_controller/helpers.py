from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorStateModel, MonitorStateResult, MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType

NOW = datetime.now(UTC)


def _async_return(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _tracked(calls, name, value=None):
    async def _call(*args, **kwargs):
        calls.append((name, args, kwargs))
        return value

    return _call


def _manager(*, http=None, api=None, ping=None, heartbeat=None, orion_script=None, incident=None, results=None, state=None, checker_factory=None):
    return MonitorManager(
        http_monitor_service=http or SimpleNamespace(),
        api_monitor_manager=api or SimpleNamespace(),
        ping_monitor_service=ping or SimpleNamespace(),
        heartbeat_monitor_service=heartbeat or SimpleNamespace(),
        incident_service=incident or SimpleNamespace(),
        monitor_result_service=results or SimpleNamespace(),
        monitor_state_service=state or SimpleNamespace(),
        checker_factory=checker_factory or SimpleNamespace(),
        orion_script_monitor_service=orion_script,
    )


def _monitor(persisted_id="m1", monitor_type=MonitorType.HTTP, timeout=30, url="http://x", name="Test"):
    return SimpleNamespace(persisted_id=persisted_id, id=persisted_id, monitor_type=monitor_type, timeout=timeout, url=url, name=name)


def _state_result(current_status, previous_status=MonitorStatus.UP, transition=MonitorTransition.NONE):
    state = MonitorStateModel(monitor_id="m1", monitor_type=MonitorType.HTTP, status=current_status)
    return MonitorStateResult(state=state, previous_status=previous_status, current_status=current_status, transition=transition)
