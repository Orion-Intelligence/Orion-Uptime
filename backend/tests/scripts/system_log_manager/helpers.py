from __future__ import annotations

from types import SimpleNamespace

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
from orion.api.interactive.system_log_manager.system_log_manager import SystemLogManager

PROFILE = SimpleNamespace(persisted_id="profile-1", login_url="HTTPS://Logs.Example.com/login", name="Primary")


def _fake_client(responses):
    calls = []

    async def get(url, params=None, headers=None):
        calls.append({"url": url, "params": params, "headers": headers})
        index = min(len(calls) - 1, len(responses) - 1)
        response = responses[index]
        if isinstance(response, Exception):
            raise response
        return response

    return SimpleNamespace(get=get), calls


def _auth_profile_service(profile=PROFILE):
    async def get_log_source_profile():
        return profile

    return SimpleNamespace(get_log_source_profile=get_log_source_profile)


def _fake_token_manager(*, token="token-1", force_refresh_token="token-2", error=None):
    calls = []

    async def get_token(profile_id, *, force_refresh=False):
        calls.append({"profile_id": profile_id, "force_refresh": force_refresh})
        if error is not None:
            raise error
        return force_refresh_token if force_refresh else token

    return SimpleNamespace(get_token=get_token), calls


def _manager(*, responses, profile=PROFILE, token_manager=None):
    client, calls = _fake_client(responses)
    manager = SystemLogManager(_auth_profile_service(profile), client=client)
    if token_manager is not None:
        auth_token_state.token_manager = token_manager
    return manager, calls
