from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.constants.constant import Cookies, OrionIntelligence
from orion.services.mongo_manager.shared_model.db_system_log_model import SystemLogEntry, SystemLogPageResponse
from orion.shared_models.exceptions import ValidationError

TYPE_KEYS = ("log_type", "type", "level", "severity")
TIME_KEYS = ("timestamp", "time", "created_at", "logged_at", "date")
FILE_KEYS = ("file", "file_name", "filename", "module", "path")
SOURCE_KEYS = ("caller", "source", "target", "function", "method", "logger", "origin")
MESSAGE_KEYS = ("message", "msg", "text", "detail", "description")
LIST_KEYS = ("logs", "data", "results", "items", "records", "entries")
TOTAL_KEYS = ("total", "count", "total_count", "total_records")


class SystemLogManager:
    def __init__(self, auth_profile_service: AuthProfileManager, client: httpx.AsyncClient | None = None):
        self.auth_profile_service = auth_profile_service
        self.client = client or httpx.AsyncClient(follow_redirects=True, timeout=30)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def get_logs(self, date: str | None, log_type: str | None, date_from: str | None, date_to: str | None, page: int, limit: int) -> SystemLogPageResponse:
        profile = await self.auth_profile_service.get_log_source_profile()
        if profile is None:
            raise ValidationError("No auth profile is selected as the log source. Open Auth profiles and choose the profile that should read the system logs.")

        token_manager = auth_token_state.token_manager
        if token_manager is None:
            raise ValidationError("Authentication service is not available.")

        params: dict[str, Any] = {"page": page, "limit": limit}
        if date:
            params["date"] = date
        if log_type and log_type.lower() != "all":
            params["log_type"] = log_type
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        url = f"{self._origin(profile.login_url)}{OrionIntelligence.SYSTEM_LOGS_PATH}"
        try:
            token = await token_manager.get_token(profile.persisted_id)
            response = await self.client.get(url, params=params, headers={"Cookie": f"{Cookies.ACCESS_TOKEN}={token}"})
            if response.status_code == 401:
                token = await token_manager.get_token(profile.persisted_id, force_refresh=True)
                response = await self.client.get(url, params=params, headers={"Cookie": f"{Cookies.ACCESS_TOKEN}={token}"})
        except auth_token_state.AuthTokenError as exc:
            raise ValidationError(f"Could not sign in with auth profile '{profile.name}': {exc}") from exc
        except httpx.HTTPError as exc:
            raise ValidationError(f"The system log request to {url} failed: {exc}") from exc

        if response.status_code != 200:
            raise ValidationError(f"Orion Intelligence returned HTTP {response.status_code} for the system logs.")

        try:
            payload = response.json()
        except ValueError:
            raise ValidationError("Orion Intelligence returned a system log response that was not valid JSON.") from None

        return self._build_page(payload, page, limit, profile.name)

    @classmethod
    def _build_page(cls, payload: Any, page: int, limit: int, profile_name: str) -> SystemLogPageResponse:
        rows: list[Any] = []
        total: int | None = None
        has_more = False

        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            container: Any = payload
            for key in ("data", "result", "response"):
                nested = container.get(key) if isinstance(container, dict) else None
                if isinstance(nested, dict):
                    container = nested
                    break
            for key in LIST_KEYS:
                candidate = container.get(key) if isinstance(container, dict) else None
                if isinstance(candidate, list):
                    rows = candidate
                    break
            if isinstance(container, dict):
                for key in TOTAL_KEYS:
                    value = container.get(key)
                    if isinstance(value, int):
                        total = value
                        break
                has_more = bool(container.get("has_more") or container.get("hasMore") or container.get("next"))

        entries = [cls._build_entry(row) for row in rows if isinstance(row, dict)]
        if total is not None:
            has_more = page * limit < total
        elif not has_more:
            has_more = len(entries) >= limit

        return SystemLogPageResponse(logs=entries, page=page, limit=limit, total=total, has_more=has_more, source_profile_name=profile_name)

    @classmethod
    def _build_entry(cls, row: dict) -> SystemLogEntry:
        return SystemLogEntry(
            type=cls._first(row, TYPE_KEYS),
            time=cls._first(row, TIME_KEYS),
            file=cls._first(row, FILE_KEYS),
            source=cls._first(row, SOURCE_KEYS),
            message=cls._first(row, MESSAGE_KEYS),
        )

    @staticmethod
    def _first(row: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None and value != "":
                return str(value)
        return ""

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url.strip())
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
