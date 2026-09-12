from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

import orion.management.managers.service_manager as service_manager
from orion.management.managers.service_manager import ServiceManager, Services
from tests.model.fakes import FakeCollection


def _async_return(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _async_noop():
    async def _call(*_args, **_kwargs):
        return None

    return _call


def _engine():
    return SimpleNamespace(database=defaultdict(FakeCollection))


def _placeholder_services(**overrides):
    fields = {name: SimpleNamespace() for name in Services._fields}
    fields.update(overrides)
    return Services(**fields)


def _overview(monitor_id, monitor_type="HTTP"):
    return SimpleNamespace(id=monitor_id, name=f"Monitor {monitor_id}", monitor_type=monitor_type, status="up", is_active=True, created_at="created", last_checked_at="checked")


def _fake_scheduler_class():
    class FakeScheduler:
        def __init__(self, monitor_service, on_fatal=None):
            self.monitor_service = monitor_service
            self.on_fatal = on_fatal
            self.started = False
            self.stopped = False

        async def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

    return FakeScheduler


def _patch_init_infra(monkeypatch, fake_services, scheduler_cls):
    configured = {}
    monkeypatch.setattr(service_manager, "EmailTemplateManager", SimpleNamespace(get_instance=lambda: SimpleNamespace(initialize=lambda: None, clear=lambda: None)))
    monkeypatch.setattr(service_manager, "db_manager", SimpleNamespace(connect=_async_noop(), disconnect=_async_noop(), engine="fake-engine"))
    monkeypatch.setattr(service_manager, "realtime_broker", SimpleNamespace(configure=lambda factory: configured.setdefault("factory", factory), shutdown=_async_noop()))
    monkeypatch.setattr(service_manager, "MonitorScheduler", scheduler_cls)
    monkeypatch.setattr(ServiceManager, "build_services", staticmethod(_async_return(fake_services)))
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin")
    return configured
