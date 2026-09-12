from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel

NOW = datetime.now(UTC)
PROFILE_ID = "64f000000000000000000002"


def _profile(login_url: str = "https://orion.example.com/api/token?cookie_only=true") -> AuthProfileModel:
    return AuthProfileModel(id=PROFILE_ID, name="Orion", login_url=login_url, credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _auth_profile_service(profiles: list[AuthProfileModel]) -> SimpleNamespace:
    profiles_by_id = {profile.id: profile for profile in profiles}

    async def get_profile_model(profile_id: str):
        return profiles_by_id.get(profile_id)

    return SimpleNamespace(get_profile_model=get_profile_model)


def _manager(handler, *, auth_profile_service=None, clock=None) -> AccessTokenCookieManager:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    kwargs = {} if clock is None else {"clock": clock}
    return AccessTokenCookieManager(auth_profile_service, client=client, **kwargs)


def _cookie_response(token: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json={"session": {}}, headers={"set-cookie": f"access_token={token}; Path=/; HttpOnly"})
