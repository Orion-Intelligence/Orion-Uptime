from __future__ import annotations

import asyncio

from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from tests.scripts.monitor_state_manager.helpers import _manager, _process


def test_failures_reach_threshold_and_transition_down(monkeypatch):
    monkeypatch.setenv("MONITOR_FAILURE_THRESHOLD", "3")
    manager, _ = _manager()

    first = _process(manager, success=False)
    assert first.transition == MonitorTransition.NONE
    assert first.current_status == MonitorStatus.UNKNOWN

    _process(manager, success=False)
    third = _process(manager, success=False)
    assert third.transition == MonitorTransition.DOWN
    assert third.current_status == MonitorStatus.DOWN


def test_recovery_from_down_transitions_up(monkeypatch):
    monkeypatch.setenv("MONITOR_FAILURE_THRESHOLD", "2")
    manager, _ = _manager()

    _process(manager, success=False)
    down = _process(manager, success=False)
    assert down.transition == MonitorTransition.DOWN

    recovery = _process(manager, success=True)
    assert recovery.transition == MonitorTransition.UP
    assert recovery.current_status == MonitorStatus.UP


def test_first_success_from_unknown_becomes_up(monkeypatch):
    monkeypatch.setenv("MONITOR_FAILURE_THRESHOLD", "3")
    manager, _ = _manager()

    result = _process(manager, success=True)
    assert result.transition == MonitorTransition.UP
    assert result.current_status == MonitorStatus.UP


def test_delete_for_monitor_removes_state(monkeypatch):
    monkeypatch.setenv("MONITOR_FAILURE_THRESHOLD", "3")
    manager, collection = _manager()
    _process(manager, success=True)
    assert len(collection.documents) == 1

    asyncio.run(manager.delete_for_monitor("monitor-1"))
    assert collection.documents == []
