from __future__ import annotations

from types import SimpleNamespace

from orion.api.interactive.monitor_config_manager.monitor_config_manager import MonitorConfigManager
from tests.model.fakes import FakeCollection


def _http_manager(*, monitor=None, create_result=None, collection=None):
    calls = {"create": [], "update": []}
    collection = collection if collection is not None else FakeCollection()

    async def get_monitor_model(_monitor_id):
        return monitor

    async def create_monitor(**kwargs):
        calls["create"].append(kwargs)
        return create_result

    async def update_monitor(**kwargs):
        calls["update"].append(kwargs)

    manager = SimpleNamespace(get_monitor_model=get_monitor_model, create_monitor=create_monitor, update_monitor=update_monitor, collection=collection)
    return manager, calls


def _api_manager(*, monitor=None, create_result=None, collection=None, auth_profile_service=None):
    calls = {"create": [], "update": []}
    collection = collection if collection is not None else FakeCollection()

    async def get_monitor_model(_monitor_id):
        return monitor

    async def create_monitor(request):
        calls["create"].append(request)
        return create_result

    async def update_monitor(monitor_id, request):
        calls["update"].append((monitor_id, request))

    manager = SimpleNamespace(get_monitor_model=get_monitor_model, create_monitor=create_monitor, update_monitor=update_monitor, collection=collection, auth_profile_service=auth_profile_service)
    return manager, calls


def _ping_manager(*, monitor=None, create_result=None, collection=None):
    calls = {"create": [], "update": []}
    collection = collection if collection is not None else FakeCollection()

    async def get_monitor_model(_monitor_id):
        return monitor

    async def create_monitor(**kwargs):
        calls["create"].append(kwargs)
        return create_result

    async def update_monitor(**kwargs):
        calls["update"].append(kwargs)

    manager = SimpleNamespace(get_monitor_model=get_monitor_model, create_monitor=create_monitor, update_monitor=update_monitor, collection=collection)
    return manager, calls


def _heartbeat_manager(*, monitor=None, create_result=None, collection=None):
    calls = {"create": [], "update": []}
    collection = collection if collection is not None else FakeCollection()

    async def get_monitor_model(_monitor_id):
        return monitor

    async def create_monitor(**kwargs):
        calls["create"].append(kwargs)
        return create_result

    async def update_monitor(monitor_id, **kwargs):
        calls["update"].append((monitor_id, kwargs))

    manager = SimpleNamespace(get_monitor_model=get_monitor_model, create_monitor=create_monitor, update_monitor=update_monitor, collection=collection)
    return manager, calls


def _manager(*, http=None, api=None, ping=None, heartbeat=None):
    http = http or _http_manager()
    api = api or _api_manager()
    ping = ping or _ping_manager()
    heartbeat = heartbeat or _heartbeat_manager()
    config_manager = MonitorConfigManager(http_monitors=http[0], api_monitors=api[0], ping_monitors=ping[0], heartbeat_monitors=heartbeat[0])
    return config_manager, {"http": http[1], "api": api[1], "ping": ping[1], "heartbeat": heartbeat[1]}


def _async_return(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _auth_profile_service(*, by_id=None, by_name=None):
    return SimpleNamespace(get_profile_model=_async_return(by_id), get_profile_model_by_name=_async_return(by_name))
