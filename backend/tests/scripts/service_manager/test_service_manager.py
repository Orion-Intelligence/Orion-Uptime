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
from orion.shared_models.exceptions import NotFoundError
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


def test_viewer_resources_groups_known_types_and_skips_unknown():
    overviews = [_overview("m1", "HTTP"), _overview("m2", "ping"), _overview("m3", "unknown")]

    resources = ServiceManager.viewer_resources(overviews)

    assert [entry["id"] for entry in resources["HTTP"]] == ["m1"]
    assert [entry["id"] for entry in resources["ping"]] == ["m2"]
    assert "unknown" not in resources
    assert resources["API"] == []
    assert set(resources) == {"HTTP", "API", "ping", "heartbeat", "orion_script", "auth_profiles", "users", "status_pages", "slack_integrations", "email_integrations"}


def test_admin_resources_gathers_every_service_listing():
    services = _placeholder_services(
        http_monitor_service=SimpleNamespace(list_monitors=_async_return(["http"])),
        api_monitor_manager=SimpleNamespace(list_monitors=_async_return(["api"])),
        ping_monitor_service=SimpleNamespace(list_monitors=_async_return(["ping"])),
        heartbeat_monitor_service=SimpleNamespace(list_monitors=_async_return(["heartbeat"])),
        orion_script_monitor_service=SimpleNamespace(list_monitors=_async_return(["orion_script"])),
        auth_profile_service=SimpleNamespace(list_profiles=_async_return(["profile"])),
        user_service=SimpleNamespace(list_users=_async_return(["user"])),
        status_page_service=SimpleNamespace(list_pages=_async_return(["page"])),
        slack_integration_service=SimpleNamespace(list_integrations=_async_return(["slack"])),
        email_integration_service=SimpleNamespace(list_integrations=_async_return(["email"])),
    )

    resources = asyncio.run(ServiceManager.admin_resources(services))

    assert resources == {
        "HTTP": ["http"],
        "API": ["api"],
        "ping": ["ping"],
        "heartbeat": ["heartbeat"],
        "orion_script": ["orion_script"],
        "auth_profiles": ["profile"],
        "users": ["user"],
        "status_pages": ["page"],
        "slack_integrations": ["slack"],
        "email_integrations": ["email"],
    }


def test_changed_monitor_details_filters_and_suppresses_not_found():
    async def get_monitor_detail(entity_id):
        if entity_id == "missing":
            raise NotFoundError("missing")
        return {"id": entity_id}

    dashboard = SimpleNamespace(get_monitor_detail=get_monitor_detail)
    changed = [("monitor", "m1"), ("monitor", None), ("status_page", "s1"), ("monitor", "missing")]

    details = asyncio.run(ServiceManager.changed_monitor_details(dashboard, changed))

    assert details == {"m1": {"id": "m1"}}


def test_build_realtime_snapshot_raises_when_services_missing():
    manager = ServiceManager()
    with pytest.raises(RuntimeError):
        asyncio.run(manager.build_realtime_snapshot([], include_admin=False))


def test_build_realtime_snapshot_common_and_admin_views():
    overviews = [_overview("m1", "HTTP")]
    dashboard = SimpleNamespace(
        get_summary=_async_return("summary"),
        get_recent_incidents=_async_return("incidents"),
        get_recent_activity=_async_return("activity"),
        get_monitor_overviews=_async_return(overviews),
        get_monitor_detail=_async_return({"id": "m1"}),
    )
    services = _placeholder_services(
        dashboard_service=dashboard,
        http_monitor_service=SimpleNamespace(list_monitors=_async_return([])),
        api_monitor_manager=SimpleNamespace(list_monitors=_async_return([])),
        ping_monitor_service=SimpleNamespace(list_monitors=_async_return([])),
        heartbeat_monitor_service=SimpleNamespace(list_monitors=_async_return([])),
        orion_script_monitor_service=SimpleNamespace(list_monitors=_async_return([])),
        auth_profile_service=SimpleNamespace(list_profiles=_async_return([])),
        user_service=SimpleNamespace(list_users=_async_return([])),
        status_page_service=SimpleNamespace(list_pages=_async_return([])),
        slack_integration_service=SimpleNamespace(list_integrations=_async_return([])),
        email_integration_service=SimpleNamespace(list_integrations=_async_return([])),
    )
    manager = ServiceManager()
    manager.services = services

    common, admin = asyncio.run(manager.build_realtime_snapshot([("monitor", "m1")], include_admin=False))
    assert common is admin
    assert common["summary"] == "summary"
    assert common["changed_monitor_details"] == {"m1": {"id": "m1"}}
    assert common["resources"]["HTTP"][0]["id"] == "m1"

    common2, admin2 = asyncio.run(manager.build_realtime_snapshot([], include_admin=True))
    assert admin2 is not common2
    assert admin2["resources"] == {"HTTP": [], "API": [], "ping": [], "heartbeat": [], "orion_script": [], "auth_profiles": [], "users": [], "status_pages": [], "slack_integrations": [], "email_integrations": []}
    assert common2["resources"]["HTTP"][0]["id"] == "m1"


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
