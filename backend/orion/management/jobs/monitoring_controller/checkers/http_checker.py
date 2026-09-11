import time

from orion.management.jobs.monitoring_controller.checkers.base_checker import CheckState, HttpCheckerBase
from orion.services.mongo_manager.shared_model.db_http_monitor_model import HTTPMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus


class HTTPChecker(HttpCheckerBase):
    async def _evaluate(self, monitor: HTTPMonitorModel, state: CheckState) -> None:
        headers = await self._build_headers(monitor)
        state.start = time.perf_counter()
        response = await self.client.get(monitor.url, headers=headers, timeout=monitor.timeout)
        if response.status_code == 401 and monitor.auth_profile_id:
            headers = await self._build_headers(monitor, force_refresh=True)
            response = await self.client.get(monitor.url, headers=headers, timeout=monitor.timeout)
        elapsed = int((time.perf_counter() - state.start) * 1000)
        state.status_code = response.status_code
        state.response_time_ms = elapsed
        status_ok = response.status_code == monitor.expected_status_code
        state.is_slow = monitor.expected_response_time_ms is not None and elapsed > monitor.expected_response_time_ms
        state.success = status_ok
        state.status = MonitorStatus.UP if state.success else MonitorStatus.DOWN

    async def _build_headers(self, monitor: HTTPMonitorModel, *, force_refresh: bool = False) -> dict[str, str]:
        if monitor.auth_profile_id is None:
            return {}
        token = await self._access_token(monitor, force_refresh=force_refresh)
        return self._cookie_header(token)
