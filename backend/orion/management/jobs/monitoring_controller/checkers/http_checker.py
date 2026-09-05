import time
from urllib.parse import urlsplit

import httpx

from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager, AuthTokenError
from orion.constants.constant import Cookies
from orion.services.mongo_manager.shared_model.db_http_monitor_model import HTTPMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import HealthCheckResponse, MonitorStatus


class HTTPChecker:
    def __init__(self, token_manager: AccessTokenCookieManager | None = None, client: httpx.AsyncClient | None = None):
        self.token_manager = token_manager
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self._owns_client = client is None

    async def check(self, monitor: HTTPMonitorModel) -> HealthCheckResponse:
        start = None
        status = MonitorStatus.DOWN
        success = False
        status_code = None
        response_time_ms = None
        is_slow = False
        error = None
        timed_out = False

        try:
            headers = await self._build_headers(monitor)
            start = time.perf_counter()
            response = await self.client.get(monitor.url, headers=headers, timeout=monitor.timeout)
            if response.status_code == 401 and monitor.auth_profile_id:
                headers = await self._build_headers(monitor, force_refresh=True)
                response = await self.client.get(monitor.url, headers=headers, timeout=monitor.timeout)
            elapsed = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            response_time_ms = elapsed
            status_ok = response.status_code == monitor.expected_status_code
            is_slow = monitor.expected_response_time_ms is not None and elapsed > monitor.expected_response_time_ms
            success = status_ok
            status = MonitorStatus.UP if success else MonitorStatus.DOWN

        except AuthTokenError as exc:
            status_code = exc.status_code
            error = f"Authentication failed: {exc}"

        except httpx.TimeoutException:
            response_time_ms = int((time.perf_counter() - start) * 1000) if start is not None else None
            timed_out = True
            error = f"The target did not complete its response within {monitor.timeout} seconds."

        except httpx.HTTPError as exc:
            response_time_ms = int((time.perf_counter() - start) * 1000) if start is not None else None
            error = self._request_error_message(exc)

        except (OSError, ValueError, RuntimeError) as exc:
            error = f"The health checker failed unexpectedly: {type(exc).__name__}."

        return HealthCheckResponse(url=monitor.url, status=status, status_code=status_code, response_time_ms=response_time_ms, success=success, is_slow=is_slow, error=error, timed_out=timed_out)

    async def _build_headers(self, monitor: HTTPMonitorModel, *, force_refresh: bool = False) -> dict[str, str]:
        if monitor.auth_profile_id is None:
            return {}
        if self.token_manager is None:
            raise AuthTokenError("The access-token cookie manager is unavailable.")
        profile = await self.token_manager.auth_profile_service.get_profile_model(monitor.auth_profile_id)
        if profile is None:
            raise AuthTokenError(f"Auth profile '{monitor.auth_profile_id}' was not found.")
        login_origin = self._origin(profile.login_url)
        if self._origin(monitor.url) != login_origin:
            raise AuthTokenError(f"The monitor URL is not on the auth profile's login origin ({login_origin}), so the session cookie was not sent.")
        token = await self.token_manager.get_token(monitor.auth_profile_id, force_refresh=force_refresh)
        return {"Cookie": f"{Cookies.ACCESS_TOKEN}={token}"}

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url.strip())
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}"

    @staticmethod
    def _request_error_message(exc: httpx.HTTPError) -> str:
        if isinstance(exc, httpx.ConnectError):
            return f"Could not connect to the target: {exc}."
        if isinstance(exc, httpx.TooManyRedirects):
            return "The target returned too many redirects."
        if isinstance(exc, httpx.RemoteProtocolError):
            return f"The target returned an invalid or incomplete HTTP response: {exc}."
        return f"The HTTP request failed before a response was received: {exc}."
