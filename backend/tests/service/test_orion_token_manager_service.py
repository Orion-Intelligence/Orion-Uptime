from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from orion.api.interactive.orion_login_manager.orion_token_manager import TOKEN_CACHE_TTL_SECONDS, AccessTokenCookieManager, AuthTokenError
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


def test_get_token_performs_login_and_caches_the_result():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _cookie_response("token-1")

    profile = _profile()
    manager = _manager(handler, auth_profile_service=_auth_profile_service([profile]))

    async def run():
        first = await manager.get_token(profile.id)
        second = await manager.get_token(profile.id)
        await manager.close()
        return first, second

    first, second = asyncio.run(run())

    assert first == "token-1"
    assert second == "token-1"
    assert len(calls) == 1


def test_get_token_raises_when_profile_does_not_exist():
    manager = _manager(lambda request: _cookie_response("token-1"), auth_profile_service=_auth_profile_service([]))

    async def run():
        with pytest.raises(AuthTokenError) as exc_info:
            await manager.get_token("missing-profile")
        await manager.close()
        return exc_info

    exc_info = asyncio.run(run())
    assert "missing-profile" in str(exc_info.value)
    assert "was not found" in str(exc_info.value)


def test_get_token_force_refresh_performs_a_new_login_and_replaces_the_cache():
    tokens = iter(["token-1", "token-2"])
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _cookie_response(next(tokens))

    profile = _profile()
    manager = _manager(handler, auth_profile_service=_auth_profile_service([profile]))

    async def run():
        first = await manager.get_token(profile.id)
        second = await manager.get_token(profile.id, force_refresh=True)
        third = await manager.get_token(profile.id)
        await manager.close()
        return first, second, third

    first, second, third = asyncio.run(run())

    assert first == "token-1"
    assert second == "token-2"
    assert third == "token-2"
    assert len(calls) == 2


def test_get_token_reauthenticates_once_the_cached_token_expires():
    tokens = iter(["token-1", "token-2"])
    current_time = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        return _cookie_response(next(tokens))

    profile = _profile()
    manager = _manager(handler, auth_profile_service=_auth_profile_service([profile]), clock=lambda: current_time[0])

    async def run():
        first = await manager.get_token(profile.id)
        current_time[0] += TOKEN_CACHE_TTL_SECONDS + 1
        second = await manager.get_token(profile.id)
        await manager.close()
        return first, second

    first, second = asyncio.run(run())

    assert first == "token-1"
    assert second == "token-2"


def test_get_token_still_uses_the_cache_before_expiry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _cookie_response("token-1")

    profile = _profile()
    current_time = [0.0]
    manager = _manager(handler, auth_profile_service=_auth_profile_service([profile]), clock=lambda: current_time[0])

    async def run():
        first = await manager.get_token(profile.id)
        current_time[0] += TOKEN_CACHE_TTL_SECONDS - 1
        second = await manager.get_token(profile.id)
        await manager.close()
        return first, second

    first, second = asyncio.run(run())

    assert first == "token-1"
    assert second == "token-1"
    assert len(calls) == 1


def test_authenticate_profile_raises_when_login_request_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    manager = _manager(handler)

    async def run():
        with pytest.raises(AuthTokenError) as exc_info:
            await manager.authenticate_profile(_profile())
        await manager.close()
        return exc_info

    exc_info = asyncio.run(run())
    assert "Login request failed" in str(exc_info.value)
    assert exc_info.value.status_code is None


def test_authenticate_profile_raises_when_login_returns_an_error_status():
    manager = _manager(lambda request: httpx.Response(401, json={"detail": "bad credentials"}))

    async def run():
        with pytest.raises(AuthTokenError) as exc_info:
            await manager.authenticate_profile(_profile())
        await manager.close()
        return exc_info

    exc_info = asyncio.run(run())
    assert exc_info.value.status_code == 401
    assert "HTTP 401" in str(exc_info.value)


def test_authenticate_profile_raises_when_access_token_cookie_is_missing():
    manager = _manager(lambda request: httpx.Response(200, json={"session": {}}))

    async def run():
        with pytest.raises(AuthTokenError) as exc_info:
            await manager.authenticate_profile(_profile())
        await manager.close()
        return exc_info

    exc_info = asyncio.run(run())
    assert exc_info.value.status_code == 200
    assert "cookie was missing" in str(exc_info.value)


def test_authenticate_profile_ignores_a_set_cookie_for_a_different_cookie_name():
    manager = _manager(lambda request: httpx.Response(200, headers={"set-cookie": "session_id=abc; Path=/"}))

    async def run():
        with pytest.raises(AuthTokenError):
            await manager.authenticate_profile(_profile())
        await manager.close()

    asyncio.run(run())


def test_get_token_propagates_authenticate_profile_failures():
    manager = _manager(lambda request: httpx.Response(500), auth_profile_service=_auth_profile_service([_profile()]))

    async def run():
        with pytest.raises(AuthTokenError) as exc_info:
            await manager.get_token(PROFILE_ID)
        await manager.close()
        return exc_info

    exc_info = asyncio.run(run())
    assert exc_info.value.status_code == 500


def test_concurrent_get_token_calls_share_a_single_login():
    login_calls = []

    async def run():
        started = asyncio.Event()
        finish = asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            login_calls.append(request)
            started.set()
            await finish.wait()
            return _cookie_response("token-1")

        manager = AccessTokenCookieManager(_auth_profile_service([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

        first_task = asyncio.create_task(manager.get_token(PROFILE_ID))
        await started.wait()
        second_task = asyncio.create_task(manager.get_token(PROFILE_ID))
        await asyncio.sleep(0)
        finish.set()

        first, second = await asyncio.gather(first_task, second_task)
        await manager.close()
        return first, second

    first, second = asyncio.run(run())

    assert first == "token-1"
    assert second == "token-1"
    assert len(login_calls) == 1


def test_invalidate_forces_a_new_login_on_the_next_get_token():
    tokens = iter(["token-1", "token-2"])

    def handler(request: httpx.Request) -> httpx.Response:
        return _cookie_response(next(tokens))

    profile = _profile()
    manager = _manager(handler, auth_profile_service=_auth_profile_service([profile]))

    async def run():
        first = await manager.get_token(profile.id)
        manager.invalidate(profile.id)
        second = await manager.get_token(profile.id)
        await manager.close()
        return first, second

    first, second = asyncio.run(run())

    assert first == "token-1"
    assert second == "token-2"


def test_invalidate_on_unknown_profile_is_a_no_op():
    manager = _manager(lambda request: _cookie_response("token-1"))
    manager.invalidate("never-cached")
    asyncio.run(manager.close())


def test_clear_forces_a_new_login_for_every_cached_profile():
    tokens = iter(["token-1", "token-2", "token-3", "token-4"])

    def handler(request: httpx.Request) -> httpx.Response:
        return _cookie_response(next(tokens))

    first_profile = _profile("https://orion.example.com/api/token?cookie_only=true")
    second_profile = AuthProfileModel(id="64f000000000000000000003", name="Second", login_url="https://orion.example.com/api/other-login", credentials={"username": "u2", "password": "p2"}, created_at=NOW, updated_at=NOW)
    manager = _manager(handler, auth_profile_service=_auth_profile_service([first_profile, second_profile]))

    async def run():
        first = await manager.get_token(first_profile.id)
        second = await manager.get_token(second_profile.id)
        manager.clear()
        third = await manager.get_token(first_profile.id)
        fourth = await manager.get_token(second_profile.id)
        await manager.close()
        return first, second, third, fourth

    first, second, third, fourth = asyncio.run(run())

    assert (first, second, third, fourth) == ("token-1", "token-2", "token-3", "token-4")


def test_close_closes_a_client_it_created_itself():
    manager = AccessTokenCookieManager(_auth_profile_service([]))

    asyncio.run(manager.close())

    assert manager.client.is_closed


def test_close_does_not_close_an_injected_client():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: _cookie_response("token-1")))
    manager = AccessTokenCookieManager(_auth_profile_service([]), client=client)

    asyncio.run(manager.close())

    assert client.is_closed is False
    asyncio.run(client.aclose())


def test_extract_access_token_cookie_prefers_the_final_response_over_history():
    earlier = httpx.Response(303, headers={"set-cookie": "access_token=stale; Path=/"})
    final = httpx.Response(200, headers={"set-cookie": "access_token=fresh; Path=/"}, history=[earlier])

    assert AccessTokenCookieManager._extract_access_token_cookie(final) == "fresh"


def test_extract_access_token_cookie_falls_back_to_history_when_final_response_has_none():
    earlier = httpx.Response(303, headers={"set-cookie": "access_token=from-redirect; Path=/"})
    final = httpx.Response(200, headers={"set-cookie": "session_id=abc; Path=/"}, history=[earlier])

    assert AccessTokenCookieManager._extract_access_token_cookie(final) == "from-redirect"


def test_extract_access_token_cookie_checks_every_set_cookie_header_on_a_response():
    response = httpx.Response(200, headers=[("set-cookie", "session_id=abc; Path=/"), ("set-cookie", "access_token=token-1; Path=/")])

    assert AccessTokenCookieManager._extract_access_token_cookie(response) == "token-1"


def test_extract_access_token_cookie_returns_none_when_no_candidate_has_it():
    earlier = httpx.Response(303, headers={"set-cookie": "session_id=abc; Path=/"})
    final = httpx.Response(200, history=[earlier])

    assert AccessTokenCookieManager._extract_access_token_cookie(final) is None
