import time
from urllib.parse import urlsplit

import httpx

from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager, AuthTokenError
from orion.constants.constant import Cookies
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import HealthCheckResponse, MonitorStatus


class CheckState:
    def __init__(self) -> None:
        self.start: float | None = None
        self.status = MonitorStatus.DOWN
        self.success = False
        self.status_code: int | None = None
        self.response_time_ms: int | None = None
        self.is_slow = False
        self.error: str | None = None
        self.timed_out = False

    def mark_elapsed(self) -> None:
        if self.start is not None:
            self.response_time_ms = int((time.perf_counter() - self.start) * 1000)

    def to_response(self, url: str) -> HealthCheckResponse:
        return HealthCheckResponse(url=url, status=self.status, status_code=self.status_code, response_time_ms=self.response_time_ms, success=self.success, is_slow=self.is_slow, error=self.error, timed_out=self.timed_out)


class HttpCheckerBase:
    checker_label = "health"

    def __init__(self, token_manager: AccessTokenCookieManager | None = None, client: httpx.AsyncClient | None = None):
        self.token_manager = token_manager
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self._owns_client = client is None

    async def check(self, monitor) -> HealthCheckResponse:
        state = CheckState()
        try:
            await self._evaluate(monitor, state)
        except AuthTokenError as exc:
            state.status_code = exc.status_code
            state.error = f"Authentication failed: {exc}"
        except httpx.TimeoutException:
            state.mark_elapsed()
            state.timed_out = True
            state.error = f"The target did not complete its response within {monitor.timeout} seconds."
        except httpx.HTTPError as exc:
            state.mark_elapsed()
            state.error = self._request_error_message(exc)
        except (OSError, ValueError, RuntimeError) as exc:
            state.error = f"The {self.checker_label} checker failed unexpectedly: {type(exc).__name__}."
        return state.to_response(monitor.url)

    async def _evaluate(self, monitor, state: CheckState) -> None:
        raise NotImplementedError

    async def _access_token(self, monitor, *, force_refresh: bool = False) -> str:
        if self.token_manager is None:
            raise AuthTokenError("The access-token cookie manager is unavailable.")
        profile = await self.token_manager.auth_profile_service.get_profile_model(monitor.auth_profile_id)
        if profile is None:
            raise AuthTokenError(f"Auth profile '{monitor.auth_profile_id}' was not found.")
        login_origin = self._origin(profile.login_url)
        if self._origin(monitor.url) != login_origin:
            raise AuthTokenError(f"The monitor URL is not on the auth profile's login origin ({login_origin}), so the session cookie was not sent.")
        return await self.token_manager.get_token(monitor.auth_profile_id, force_refresh=force_refresh)

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

    def _cookie_header(self, token: str) -> dict[str, str]:
        return {"Cookie": f"{Cookies.ACCESS_TOKEN}={token}"}
