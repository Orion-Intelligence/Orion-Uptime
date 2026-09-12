from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from orion.management.jobs.monitoring_controller.checkers.api_checker import ApiChecker
from orion.management.jobs.monitoring_controller.checkers.checker_factory import CheckerFactory
from orion.management.jobs.monitoring_controller.checkers.heartbeat_checker import HeartbeatChecker
from orion.management.jobs.monitoring_controller.checkers.http_checker import HTTPChecker
from orion.management.jobs.monitoring_controller.checkers.orion_script_checker import OrionScriptChecker
from orion.management.jobs.monitoring_controller.checkers.ping_checker import PingChecker
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType


def test_factory_returns_the_checker_for_each_type():
    factory = CheckerFactory()
    assert isinstance(factory.get_checker(MonitorType.HTTP), HTTPChecker)
    assert isinstance(factory.get_checker(MonitorType.API), ApiChecker)
    assert isinstance(factory.get_checker(MonitorType.PING), PingChecker)
    assert isinstance(factory.get_checker(MonitorType.HEARTBEAT), HeartbeatChecker)
    assert isinstance(factory.get_checker(MonitorType.ORION_SCRIPT), OrionScriptChecker)


def test_factory_rejects_unsupported_type():
    factory = CheckerFactory()
    with pytest.raises(ValueError):
        factory.get_checker("not-a-monitor-type")


def test_factory_close_closes_checkers_and_token_manager():
    closed = {"token": False}

    async def close_token():
        closed["token"] = True

    token_manager = SimpleNamespace(close=close_token)
    factory = CheckerFactory(token_manager=token_manager)

    asyncio.run(factory.close())
    assert closed["token"] is True
