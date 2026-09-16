from __future__ import annotations

import asyncio
import logging
import os
import signal
from types import SimpleNamespace

import pytest

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
import orion.management.managers.service_manager as service_manager
from orion.management.managers.service_manager import ServiceManager, Services
from tests.scripts.service_manager.fixtures import reset_service_manager
from tests.scripts.service_manager.helpers import _async_noop, _async_return, _engine, _fake_scheduler_class, _overview, _patch_init_infra, _placeholder_services


def test_get_instance_returns_singleton():
    first = ServiceManager.get_instance()
    second = ServiceManager.get_instance()
    assert first is second
    assert isinstance(first, ServiceManager)


def test_build_services_wires_dependencies():
    services = asyncio.run(ServiceManager.build_services(_engine()))

    assert isinstance(services, Services)
    assert services.monitor_service.http_monitor_service is services.http_monitor_service
    assert services.monitor_service.api_monitor_service is services.api_monitor_manager
    assert services.monitor_service.ping_monitor_service is services.ping_monitor_service
    assert services.monitor_service.heartbeat_monitor_service is services.heartbeat_monitor_service
    assert services.monitor_service.orion_script_monitor_service is services.orion_script_monitor_service
    assert services.monitor_service.slack_integration_service is services.slack_integration_service
    assert services.monitor_service.email_integration_service is services.email_integration_service
    assert services.heartbeat_monitor_service.monitor_service is services.monitor_service
    assert services.status_page_service.monitor_service is services.monitor_service
    assert services.status_page_service.dashboard_service is services.dashboard_service
    assert services.dashboard_service.monitor_service is services.monitor_service
    assert services.dashboard_service.incident_service is services.monitor_service.incident_service
    assert services.dashboard_service.monitor_result_service is services.monitor_service.monitor_result_service
    assert services.http_monitor_service.auth_profile_service is services.auth_profile_service
    assert services.api_monitor_manager.auth_profile_service is services.auth_profile_service
    assert services.orion_script_monitor_service.auth_profile_service is services.auth_profile_service
    assert services.monitor_service.checker_factory is services.checker_factory
    assert auth_token_state.token_manager is not None
    assert auth_token_state.token_manager.auth_profile_service is services.auth_profile_service


def test_changed_monitor_details_forwards_only_monitor_ids():
    received = {}

    async def build_monitor_details(overviews, monitor_ids):
        received["overviews"] = overviews
        received["monitor_ids"] = list(monitor_ids)
        return {monitor_id: {"id": monitor_id} for monitor_id in monitor_ids if monitor_id != "missing"}

    dashboard = SimpleNamespace(build_monitor_details=build_monitor_details)
    changed = [("monitor", "m1"), ("monitor", None), ("status_page", "s1"), ("monitor", "missing")]
    overviews = [_overview("m1", "HTTP")]

    details = asyncio.run(ServiceManager.changed_monitor_details(dashboard, changed, overviews))

    assert received["monitor_ids"] == ["m1", "missing"]
    assert received["overviews"] is overviews
    assert details == {"m1": {"id": "m1"}}


def test_changed_monitor_details_skips_lookup_without_monitor_changes():
    async def build_monitor_details(overviews, monitor_ids):
        raise AssertionError("build_monitor_details should not be called")

    dashboard = SimpleNamespace(build_monitor_details=build_monitor_details)

    assert asyncio.run(ServiceManager.changed_monitor_details(dashboard, [("status_page", "s1")], [])) == {}


def test_build_realtime_snapshot_raises_when_services_missing():
    manager = ServiceManager()
    with pytest.raises(RuntimeError):
        asyncio.run(manager.build_realtime_snapshot([]))


def test_build_realtime_snapshot_returns_encoded_sections():
    overviews = [_overview("m1", "HTTP")]
    detail_calls = []

    async def build_monitor_details(passed_overviews, monitor_ids):
        detail_calls.append((passed_overviews, list(monitor_ids)))
        return {monitor_id: {"id": monitor_id} for monitor_id in monitor_ids}

    dashboard = SimpleNamespace(
        collect_snapshot_sections=_async_return(("summary", "incidents", "activity", overviews)),
        build_monitor_details=build_monitor_details,
    )
    manager = ServiceManager()
    manager.services = _placeholder_services(dashboard_service=dashboard)

    snapshot = asyncio.run(manager.build_realtime_snapshot([("monitor", "m1")]))

    assert snapshot["summary"] == "summary"
    assert snapshot["changed_monitor_details"] == {"m1": {"id": "m1"}}
    assert snapshot["overviews"][0]["id"] == "m1"
    assert isinstance(snapshot["generated_at"], str)
    assert "resources" not in snapshot
    assert detail_calls == [(overviews, ["m1"])]


def test_init_services_and_shutdown_wire_scheduler_and_teardown(monkeypatch):
    fake_services = _placeholder_services(
        user_service=SimpleNamespace(default_admin_password_in_use=_async_return(False)),
        checker_factory=SimpleNamespace(close=_async_noop()),
        slack_integration_service=SimpleNamespace(close=_async_noop()),
    )
    configured = _patch_init_infra(monkeypatch, fake_services, _fake_scheduler_class())

    manager = ServiceManager()

    async def scenario():
        services = await manager.init_services()
        await asyncio.sleep(0)
        assert services is fake_services
        assert scheduler_state.scheduler is not None
        assert scheduler_state.scheduler.started is True
        assert configured["factory"] == manager.build_realtime_snapshot
        assert manager.scheduler_task is not None
        assert manager.watchdog_task is not None
        await manager.shutdown()

    asyncio.run(scenario())

    assert scheduler_state.scheduler.stopped is True
    assert manager.services is None
    assert auth_token_state.token_manager is None
    assert manager.scheduler_task.cancelled() or manager.scheduler_task.done()
    assert manager.watchdog_task.cancelled() or manager.watchdog_task.done()


def test_shutdown_without_prior_init_is_a_no_op(monkeypatch):
    fake_realtime_broker = SimpleNamespace(shutdown=_async_noop())
    fake_template_manager = SimpleNamespace(initialize=lambda: None, clear=lambda: None)
    fake_db_manager = SimpleNamespace(disconnect=_async_noop())

    monkeypatch.setattr(service_manager, "EmailTemplateManager", SimpleNamespace(get_instance=lambda: fake_template_manager))
    monkeypatch.setattr(service_manager, "db_manager", fake_db_manager)
    monkeypatch.setattr(service_manager, "realtime_broker", fake_realtime_broker)

    manager = ServiceManager()
    asyncio.run(manager.shutdown())

    assert manager.services is None


def test_init_services_warns_when_default_admin_password_still_in_use(monkeypatch, caplog):
    fake_services = _placeholder_services(
        user_service=SimpleNamespace(default_admin_password_in_use=_async_return(True)),
        checker_factory=SimpleNamespace(close=_async_noop()),
        slack_integration_service=SimpleNamespace(close=_async_noop()),
    )
    _patch_init_infra(monkeypatch, fake_services, _fake_scheduler_class())

    manager = ServiceManager()

    async def scenario():
        with caplog.at_level(logging.WARNING, logger="orion.uptime"):
            await manager.init_services()
        await manager.shutdown()

    asyncio.run(scenario())

    assert "DEFAULT_ADMIN_PASSWORD" in caplog.text


def test_terminate_process_logs_and_signals_self(monkeypatch):
    calls = []
    monkeypatch.setattr(service_manager.os, "kill", lambda pid, sig: calls.append((pid, sig)))

    service_manager.terminate_process("boom")

    assert calls == [(os.getpid(), signal.SIGTERM)]


def test_scheduler_watchdog_terminates_when_scheduler_is_unhealthy(monkeypatch):
    terminated = {}

    def fake_terminate(reason):
        terminated["reason"] = reason

    monkeypatch.setattr(service_manager, "terminate_process", fake_terminate)
    fake_scheduler = SimpleNamespace(running=True, last_reconcile_at=1.0, is_healthy=lambda _seconds: False)

    asyncio.run(asyncio.wait_for(service_manager.scheduler_watchdog(fake_scheduler, interval=0), timeout=5))

    assert "not reconciled" in terminated["reason"]


def test_scheduler_watchdog_keeps_waiting_while_scheduler_is_healthy():
    fake_scheduler = SimpleNamespace(running=True, last_reconcile_at=1.0, is_healthy=lambda _seconds: True)

    async def scenario():
        task = asyncio.create_task(service_manager.scheduler_watchdog(fake_scheduler, interval=0))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
