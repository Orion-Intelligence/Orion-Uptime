from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, TypeGuard

import httpx

from app.service.mongo_db.shared_models.db_orion_login_model import AuthProfileModel

if TYPE_CHECKING:
    from app.modules.orion_login_manager.orion_login_manager import AuthProfileManager

ACCESS_TOKEN_COOKIE_NAME = "access_token"
TOKEN_CACHE_TTL_SECONDS = 14 * 60

class AuthTokenError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)

@dataclass(frozen=True)
class CachedAccessToken:
    value: str
    expires_at: float

class AccessTokenCookieManager:
    def __init__(self, auth_profile_service: AuthProfileManager, client: httpx.AsyncClient | None = None, clock: Callable[[], float] = time.monotonic):
        self.auth_profile_service = auth_profile_service
        self.client = client or httpx.AsyncClient(follow_redirects=True)
        self.clock = clock
        self._owns_client = client is None
        self._cache: dict[str, CachedAccessToken] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_token(self, profile_id: str, *, force_refresh: bool = False) -> str:
        cached = self._cache.get(profile_id)
        if not force_refresh and self._is_valid(cached):
            return cached.value

        lock = self._locks.setdefault(profile_id, asyncio.Lock())
        async with lock:
            cached = self._cache.get(profile_id)
            if not force_refresh and self._is_valid(cached):
                return cached.value

            profile = await self.auth_profile_service.get_profile_model(profile_id)
            if profile is None:
                raise AuthTokenError(f"Auth profile '{profile_id}' was not found.")

            token, _ = await self.authenticate_profile(profile)
            self.cache_token(profile_id, token)
            return token

    async def authenticate_profile(self, profile: AuthProfileModel) -> tuple[str, int]:
        try:
            response = await self.client.post(
                url=profile.login_url,
                headers=profile.headers,
                data=profile.credentials,
            )
        except httpx.RequestError as exc:
            raise AuthTokenError(
                f"Login request failed for profile '{profile.name}': {exc}"
            ) from exc

        if not response.is_success:
            raise AuthTokenError(
                f"Login returned HTTP {response.status_code}. Auth profile was not created.",
                status_code=response.status_code,
            )

        token = self._extract_access_token_cookie(response)
        if token is None:
            raise AuthTokenError(
                f"Login returned HTTP {response.status_code}, but the "
                f"'{ACCESS_TOKEN_COOKIE_NAME}' cookie was missing. Auth profile was not created.",
                status_code=response.status_code,
            )

        return token, response.status_code

    def cache_token(self, profile_id: str, token: str) -> None:
        self._cache[profile_id] = CachedAccessToken(
            value=token,
            expires_at=self.clock() + TOKEN_CACHE_TTL_SECONDS,
        )

    def invalidate(self, profile_id: str) -> None:
        self._cache.pop(profile_id, None)

    def clear(self) -> None:
        self._cache.clear()

    async def close(self) -> None:
        self.clear()
        if self._owns_client:
            await self.client.aclose()

    def _is_valid(self, cached: CachedAccessToken | None) -> TypeGuard[CachedAccessToken]:
        return cached is not None and self.clock() < cached.expires_at

    @staticmethod
    def _extract_access_token_cookie(response: httpx.Response) -> str | None:
        for candidate in reversed([*response.history, response]):
            for header in candidate.headers.get_list("set-cookie"):
                cookies = SimpleCookie()
                cookies.load(header)
                morsel = cookies.get(ACCESS_TOKEN_COOKIE_NAME)
                if morsel is not None and morsel.value:
                    return morsel.value
        return None

token_manager: AccessTokenCookieManager | None = None
