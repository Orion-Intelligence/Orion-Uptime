from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel


def test_authenticate_profile_does_not_replay_a_previous_session_cookie():
    cookies_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        cookies_seen.append(request.headers.get("cookie"))
        if request.headers.get("cookie"):
            return httpx.Response(401, json={"detail": "Missing or invalid token"})
        return httpx.Response(200, json={"session": {}}, headers={"set-cookie": "access_token=token-1; Path=/; HttpOnly"})

    now = datetime.now(UTC)
    profile = AuthProfileModel(id="p1", name="Orion", login_url="https://orion.example.com/api/token?cookie_only=true", credentials={"username": "u", "password": "p"}, created_at=now, updated_at=now)
    manager = AccessTokenCookieManager(None, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def run():
        first = await manager.authenticate_profile(profile)
        second = await manager.authenticate_profile(profile)
        await manager.close()
        return first, second

    first, second = asyncio.run(run())

    assert first == ("token-1", 200)
    assert second == ("token-1", 200)
    assert cookies_seen == [None, None]
