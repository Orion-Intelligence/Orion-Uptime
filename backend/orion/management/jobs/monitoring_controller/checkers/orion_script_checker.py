from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager, AuthTokenError
from orion.constants.constant import Cookies, OrionIntelligence
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionFeederStatus, OrionScriptCheckResponse, OrionScriptMonitorModel

MESSAGE_MAX_LENGTH = 500
VALUE_STATUSES = {"success": MonitorStatus.UP, "failure": MonitorStatus.DOWN}


class FeederFetchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class OrionScriptChecker:
    def __init__(self, token_manager: AccessTokenCookieManager | None = None, client: httpx.AsyncClient | None = None):
        self.token_manager = token_manager
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self._owns_client = client is None

    async def check(self, monitor: OrionScriptMonitorModel) -> OrionScriptCheckResponse:
        start = None
        status = MonitorStatus.DOWN
        success = False
        status_code = None
        response_time_ms = None
        is_slow = False
        error = None
        timed_out = False
        feeders: list[OrionFeederStatus] = []
        try:
            profile = await self._resolve_profile(monitor.url)
            start = time.perf_counter()
            scripts, status_code = await self._fetch_scripts(monitor, profile.persisted_id)
            response_time_ms = int((time.perf_counter() - start) * 1000)
            feeders = self.build_feeders(scripts)
            if not feeders:
                raise FeederFetchError(f"Orion Intelligence returned {len(scripts)} feeder scripts, but none could be read. Fields received: {', '.join(sorted(scripts[0]))}.", status_code)
            is_slow = monitor.expected_response_time_ms is not None and response_time_ms > monitor.expected_response_time_ms
            success = True
            status = MonitorStatus.UP
        except AuthTokenError as exc:
            status_code = exc.status_code
            error = f"Authentication failed: {exc}"
        except FeederFetchError as exc:
            status_code = exc.status_code
            response_time_ms = int((time.perf_counter() - start) * 1000) if start is not None else None
            error = str(exc)
        except httpx.TimeoutException:
            if start is not None:
                response_time_ms = int((time.perf_counter() - start) * 1000)
            timed_out = True
            error = f"Orion Intelligence did not return the feeder list within {monitor.timeout} seconds."
        except httpx.HTTPError as exc:
            if start is not None:
                response_time_ms = int((time.perf_counter() - start) * 1000)
            error = f"The feeder list request failed before a response was received: {exc}."
        except (OSError, ValueError, RuntimeError) as exc:
            error = f"The Orion script checker failed unexpectedly: {type(exc).__name__}."

        return OrionScriptCheckResponse(url=monitor.url, status=status, status_code=status_code, response_time_ms=response_time_ms, success=success, is_slow=is_slow, error=error, timed_out=timed_out, feeders=feeders)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @classmethod
    def find_profile(cls, profiles: list[AuthProfileModel], url: str) -> AuthProfileModel | None:
        origin = cls._origin(url)
        return next((profile for profile in profiles if cls._origin(profile.login_url) == origin), None)

    async def _resolve_profile(self, url: str) -> AuthProfileModel:
        if self.token_manager is None:
            raise AuthTokenError("The access-token cookie manager is unavailable.")
        profile = self.find_profile(await self.token_manager.auth_profile_service.list_profile_models(), url)
        if profile is None:
            raise AuthTokenError(f"No auth profile logs into {self._origin(url)}. Create an auth profile for that Orion Intelligence instance first.")
        return profile

    async def _fetch_scripts(self, monitor: OrionScriptMonitorModel, profile_id: str) -> tuple[list[dict], int | None]:
        if self.token_manager is None:
            raise AuthTokenError("The access-token cookie manager is unavailable.")
        token = await self.token_manager.get_token(profile_id)
        scripts: list[dict] = []
        status_code = None
        for page in range(1, OrionIntelligence.FEEDER_MAX_PAGES + 1):
            response = await self._request(monitor, token, page)
            if response.status_code == 401:
                token = await self.token_manager.get_token(profile_id, force_refresh=True)
                response = await self._request(monitor, token, page)
            status_code = response.status_code
            if response.status_code != 200:
                raise FeederFetchError(f"Orion Intelligence returned HTTP {response.status_code} for the feeder script list.", response.status_code)
            try:
                payload = response.json()
            except ValueError:
                raise FeederFetchError("Orion Intelligence returned a feeder script list that was not valid JSON.", response.status_code) from None
            if not isinstance(payload, dict) or not isinstance(payload.get("scripts"), list):
                raise FeederFetchError("Orion Intelligence returned a feeder script list without a scripts array.", response.status_code)
            scripts.extend(item for item in payload["scripts"] if isinstance(item, dict))
            if not payload.get("has_more"):
                break
        if not scripts:
            raise FeederFetchError("Orion Intelligence returned no feeder scripts for this auth profile. Only administrator accounts can see every feeder script; other accounts only see scripts they own.", status_code)
        return scripts, status_code

    async def _request(self, monitor: OrionScriptMonitorModel, token: str, page: int) -> httpx.Response:
        url = f"{monitor.url.rstrip('/')}{OrionIntelligence.FEEDER_SCRIPTS_PATH}"
        return await self.client.get(url, params={"page": page, "limit": OrionIntelligence.FEEDER_PAGE_LIMIT}, headers={"Cookie": f"{Cookies.ACCESS_TOKEN}={token}"}, timeout=monitor.timeout)

    @classmethod
    def build_feeders(cls, scripts: list[dict]) -> list[OrionFeederStatus]:
        feeders: list[OrionFeederStatus] = []
        seen: set[str] = set()
        for script in scripts:
            script_id = str(script.get("id") or "").strip()
            if not script_id:
                continue
            rule_key = script.get("rule_key") or None
            enabled = script.get("enabled") is not False
            if script.get("entry_kind") != "values":
                status, checked_at, message = cls._script_status(script)
                cls._append(feeders, seen, OrionFeederStatus(key=script_id, name=str(script.get("file_name") or script_id), rule_key=rule_key, status=status, enabled=enabled, last_checked_at=checked_at, message=message))
            for value in script.get("values") or []:
                if not isinstance(value, dict):
                    continue
                value_url = str(value.get("url") or "").strip()
                if not value_url:
                    continue
                digest = hashlib.sha256(value_url.encode()).hexdigest()[:12]
                status = VALUE_STATUSES.get(str(value.get("status") or "").lower(), MonitorStatus.UNKNOWN)
                message = value.get("last_error") if status == MonitorStatus.DOWN else value.get("last_success_message")
                cls._append(feeders, seen, OrionFeederStatus(key=f"{script_id}{OrionIntelligence.FEEDER_RESULT_SEPARATOR}{digest}", name=value_url, rule_key=rule_key, status=status, enabled=enabled, last_checked_at=cls._parse_datetime(value.get("last_checked_at")), message=cls._trim(message)))
        return feeders

    @staticmethod
    def _append(feeders: list[OrionFeederStatus], seen: set[str], feeder: OrionFeederStatus) -> None:
        if feeder.key in seen:
            return
        seen.add(feeder.key)
        feeders.append(feeder)

    @classmethod
    def _script_status(cls, script: dict) -> tuple[MonitorStatus, datetime | None, str | None]:
        success_at = cls._parse_datetime(script.get("last_success_date"))
        failure_at = cls._parse_datetime(script.get("last_failure_date"))
        if success_at is None and failure_at is None:
            return MonitorStatus.UNKNOWN, None, None
        if failure_at is None or (success_at is not None and success_at >= failure_at):
            return MonitorStatus.UP, success_at, cls._trim(script.get("last_success_message"))
        return MonitorStatus.DOWN, failure_at, cls._trim(script.get("last_failure_message"))

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _trim(message: object) -> str | None:
        if not isinstance(message, str):
            return None
        message = message.strip()
        if not message:
            return None
        return message[:MESSAGE_MAX_LENGTH]

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url.strip())
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
