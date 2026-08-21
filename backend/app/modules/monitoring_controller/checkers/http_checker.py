import time

import httpx

from app.service.mongo_db.shared_models.db_http_monitor_model import HTTPMonitorModel
from app.service.mongo_db.shared_models.db_monitoring_controller_model import HealthCheckResponse, MonitorStatus


class HTTPChecker:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self._owns_client = client is None

    async def check(self, monitor: HTTPMonitorModel) -> HealthCheckResponse:
        start = time.perf_counter()
        status = MonitorStatus.DOWN
        success = False
        status_code = None
        response_time_ms = None
        is_slow = False
        error = None
        timed_out = False

        try:
            response = await self.client.get(monitor.url, timeout=monitor.timeout)
            elapsed = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            response_time_ms = elapsed
            status_ok = response.status_code == monitor.expected_status_code
            is_slow = monitor.expected_response_time_ms is not None and elapsed > monitor.expected_response_time_ms
            success = status_ok
            status = MonitorStatus.UP if success else MonitorStatus.DOWN

        except httpx.TimeoutException:
            response_time_ms = int((time.perf_counter() - start) * 1000)
            timed_out = True
            error = (
                f"The target did not complete its response within "
                f"{monitor.timeout} seconds."
            )

        except httpx.HTTPError as exc:
            response_time_ms = int((time.perf_counter() - start) * 1000)
            error = self._request_error_message(exc)

        except Exception as exc:
            error = f"The health checker failed unexpectedly: {type(exc).__name__}."

        return HealthCheckResponse(
            url=monitor.url,
            status=status,
            status_code=status_code,
            response_time_ms=response_time_ms,
            success=success,
            is_slow=is_slow,
            error=error,
            timed_out=timed_out,
        )

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def _request_error_message(exc: httpx.HTTPError) -> str:
        if isinstance(exc, httpx.ConnectError):
            return f"Could not connect to the target: {exc}."
        if isinstance(exc, httpx.TooManyRedirects):
            return "The target returned too many redirects."
        if isinstance(exc, httpx.RemoteProtocolError):
            return f"The target returned an invalid or incomplete HTTP response: {exc}."
        return f"The HTTP request failed before a response was received: {exc}."
