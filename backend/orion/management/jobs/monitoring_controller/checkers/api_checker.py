import time

from orion.api.interactive.api_monitor_manager.json_matcher import json_matches
from orion.management.jobs.monitoring_controller.checkers.base_checker import CheckState, HttpCheckerBase
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus


class ApiChecker(HttpCheckerBase):
    checker_label = "API"

    async def _evaluate(self, monitor, state: CheckState) -> None:
        headers = await self._build_headers(monitor)
        state.start = time.perf_counter()
        response = await self.client.request(method=monitor.method, url=monitor.url, headers=headers, json=monitor.request_body or None, timeout=monitor.timeout)

        if response.status_code == 401 and monitor.auth_profile_id:
            headers = await self._build_headers(monitor, force_refresh=True)
            response = await self.client.request(method=monitor.method, url=monitor.url, headers=headers, json=monitor.request_body or None, timeout=monitor.timeout)

        elapsed = int((time.perf_counter() - state.start) * 1000)
        state.status_code = response.status_code
        state.response_time_ms = elapsed
        status_ok = response.status_code == monitor.expected_status_code

        try:
            response_json = response.json()
        except ValueError:
            response_json = None

        json_ok = json_matches(monitor.expected_json, response_json) if monitor.expected_json else True

        headers_ok = True
        if monitor.expected_headers:
            for key, expected in monitor.expected_headers.items():
                actual = response.headers.get(key)
                if actual != expected:
                    headers_ok = False
                    break

        content_type_ok = True
        if monitor.expected_content_type:
            actual = response.headers.get("Content-Type", "")
            content_type_ok = monitor.expected_content_type.lower() in actual.lower()

        state.is_slow = monitor.expected_response_time_ms is not None and elapsed > monitor.expected_response_time_ms
        state.success = status_ok and json_ok and headers_ok and content_type_ok
        state.status = MonitorStatus.UP if state.success else MonitorStatus.DOWN

        if not state.success:
            if not status_ok:
                pass
            elif not json_ok:
                state.error = "The response JSON did not match the configured expected JSON."
            elif not headers_ok:
                state.error = "One or more response headers did not match the configured expected headers."
            elif not content_type_ok:
                actual_content_type = response.headers.get("Content-Type") or "not provided"
                state.error = f"Expected Content-Type '{monitor.expected_content_type}', but received '{actual_content_type}'."

    async def _build_headers(self, monitor, *, force_refresh: bool = False) -> dict[str, str]:
        headers = dict(monitor.headers or {})
        if monitor.auth_profile_id is None:
            return headers
        token = await self._access_token(monitor, force_refresh=force_refresh)
        headers = {key: value for key, value in headers.items() if key.lower() not in {"authorization", "cookie"}}
        headers.update(self._cookie_header(token))
        return headers
