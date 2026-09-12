from __future__ import annotations

import httpx

from orion.management.jobs.monitoring_controller.checkers.base_checker import HttpCheckerBase
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from tests.model.fakes import FakeTokenManager


class _ExplodingTokenManager(FakeTokenManager):
    async def _list_profiles(self):
        raise RuntimeError("boom")


class _TimeoutOnListTokenManager(FakeTokenManager):
    async def _list_profiles(self):
        raise httpx.TimeoutException("slow", request=httpx.Request("GET", "https://x"))


class _HttpErrorOnListTokenManager(FakeTokenManager):
    async def _list_profiles(self):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))


class _ScriptedChecker(HttpCheckerBase):
    def __init__(self, action, **kwargs):
        super().__init__(**kwargs)
        self._action = action

    async def _evaluate(self, monitor, state):
        await self._action(state)


class _AccessTokenChecker(HttpCheckerBase):
    async def _evaluate(self, monitor, state):
        await self._access_token(monitor)
        state.success = True
        state.status = MonitorStatus.UP
