import time
from urllib.parse import urlsplit

import httpx

from app.modules.api_monitor_manager.json_matcher import json_matches
from app.modules.orion_login_manager.orion_token_manager import ACCESS_TOKEN_COOKIE_NAME, AccessTokenCookieManager, AuthTokenError
from app.service.mongo_db.shared_models.db_monitoring_controller_model import HealthCheckResponse, MonitorStatus


class ApiChecker:
    def __init__(self, token_manager: AccessTokenCookieManager | None = None, client: httpx.AsyncClient | None = None):
        self.token_manager = token_manager
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self._owns_client = client is None

    async def check(self, monitor) -> HealthCheckResponse:
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
            response = await self.client.request(
                method=monitor.method,
                url=monitor.url,
                headers=headers,
                json=monitor.request_body or None,
                timeout=monitor.timeout,
            )

            if response.status_code == 401 and monitor.auth_profile_id:
                headers = await self._build_headers(monitor, force_refresh=True)
                response = await self.client.request(
                    method=monitor.method,
                    url=monitor.url,
                    headers=headers,
                    json=monitor.request_body or None,
                    timeout=monitor.timeout,
                )

            elapsed = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            response_time_ms = elapsed
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

            is_slow = monitor.expected_response_time_ms is not None and elapsed > monitor.expected_response_time_ms

            success = status_ok and json_ok and headers_ok and content_type_ok
            status = MonitorStatus.UP if success else MonitorStatus.DOWN

            if not success:
                if not status_ok:
                    pass
                elif not json_ok:
                    error = "The response JSON did not match the configured expected JSON."
                elif not headers_ok:
                    error = "One or more response headers did not match the configured expected headers."
                elif not content_type_ok:
                    actual_content_type = response.headers.get("Content-Type") or "not provided"
                    error = (
                        f"Expected Content-Type '{monitor.expected_content_type}', "
                        f"but received '{actual_content_type}'."
                    )
        except AuthTokenError as exc:
            status_code = exc.status_code
            error = f"Authentication failed: {exc}"

        except httpx.TimeoutException:
            if start is not None:
                response_time_ms = int((time.perf_counter() - start) * 1000)
            timed_out = True
            error = (
                f"The target did not complete its response within "
                f"{monitor.timeout} seconds."
            )

        except httpx.HTTPError as exc:
            if start is not None:
                response_time_ms = int((time.perf_counter() - start) * 1000)
            error = self._request_error_message(exc)

        except Exception as exc:
            error = f"The API checker failed unexpectedly: {type(exc).__name__}."

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

    async def _build_headers(self, monitor, *, force_refresh: bool = False) -> dict[str, str]:
        headers = dict(monitor.headers or {})
        if monitor.auth_profile_id is None:
            return headers
        if self.token_manager is None:
            raise AuthTokenError("The access-token cookie manager is unavailable.")

        profile = await self.token_manager.auth_profile_service.get_profile_model(monitor.auth_profile_id)
        if profile is None:
            raise AuthTokenError(f"Auth profile '{monitor.auth_profile_id}' was not found.")
        login_origin = self._origin(profile.login_url)
        if self._origin(monitor.url) != login_origin:
            raise AuthTokenError(f"The monitor URL is not on the auth profile's login origin ({login_origin}), so the session cookie was not sent.")

        token = await self.token_manager.get_token(
            monitor.auth_profile_id,
            force_refresh=force_refresh,
        )

        headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in {"authorization", "cookie"}
        }
        headers["Cookie"] = f"{ACCESS_TOKEN_COOKIE_NAME}={token}"
        return headers

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
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
