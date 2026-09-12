from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId

from orion.api.interactive.auth_manager.auth_manager import LoginThrottle, PasswordManager, RefreshTokenManager, RevokedAccessTokens
from orion.constants.constant import Limits
from orion.services.mongo_manager.shared_model.db_user_account_model import UserModel, UserRole
from orion.shared_models.exceptions import AuthenticationError, NotFoundError, RateLimitError
from tests.scripts.auth_manager.helpers import NOW, PASSWORD, _auth_manager, _store_user


def test_login_throttle_locks_after_repeated_failures_and_clears_on_success():
    clock = {"t": 100.0}
    throttle = LoginThrottle(clock=lambda: clock["t"])

    for _ in range(Limits.LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP):
        throttle.record_failure("1.2.3.4", "alice")

    with pytest.raises(RateLimitError):
        throttle.check("1.2.3.4", "alice")

    clock["t"] += 15 * 60 + 1
    throttle.check("1.2.3.4", "alice")
    throttle.record_success("1.2.3.4", "alice")


def test_revoked_access_tokens_track_and_expire():
    clock = {"t": 0.0}
    revoked = RevokedAccessTokens(clock=lambda: clock["t"])
    revoked.revoke("jti-1", expires_at=100.0)

    assert revoked.is_revoked("jti-1") is True
    assert revoked.is_revoked(None) is False

    clock["t"] = 200.0
    assert revoked.is_revoked("jti-1") is False


def test_password_and_refresh_token_hashing_round_trip():
    password_manager = PasswordManager()
    hashed = password_manager.hash_password(PASSWORD)
    assert password_manager.verify_password(PASSWORD, hashed) is True
    assert password_manager.verify_password("wrong-password", hashed) is False

    refresh_manager = RefreshTokenManager()
    token_hash = refresh_manager.hash_token("refresh-token")
    assert refresh_manager.verify_token("refresh-token", token_hash) is True
    assert refresh_manager.verify_token("other", token_hash) is False


def test_login_succeeds_and_issues_tokens():
    manager, collection = _auth_manager()
    _store_user(collection)

    tokens = asyncio.run(manager.login("alice", PASSWORD))
    assert tokens.access_token
    assert tokens.refresh_token
    assert manager.jwt_service.verify_refresh_token(tokens.refresh_token)["sub"]


def test_login_rejects_bad_password_missing_user_and_disabled():
    manager, collection = _auth_manager()
    _store_user(collection)

    with pytest.raises(AuthenticationError):
        asyncio.run(manager.login("alice", "wrong-password"))
    with pytest.raises(AuthenticationError):
        asyncio.run(manager.login("ghost", PASSWORD))

    manager2, collection2 = _auth_manager()
    _store_user(collection2, is_active=False)
    with pytest.raises(AuthenticationError):
        asyncio.run(manager2.login("alice", PASSWORD))


def test_get_current_user_paths():
    manager, collection = _auth_manager()
    user_id = _store_user(collection)

    current = asyncio.run(manager.get_current_user(user_id))
    assert current.username == "alice"
    assert current.role == UserRole.ADMIN

    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_current_user("not-valid"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_current_user(str(ObjectId())))


def test_get_current_user_rejects_disabled_account():
    manager, collection = _auth_manager()
    user_id = _store_user(collection, is_active=False)
    with pytest.raises(AuthenticationError):
        asyncio.run(manager.get_current_user(user_id))


def test_logout_clears_refresh_state():
    manager, collection = _auth_manager()
    user_id = _store_user(collection, refresh_hash="hash", refresh_expires=NOW + timedelta(days=1))

    asyncio.run(manager.logout(user_id))
    assert collection.documents[0]["refresh_token_hash"] is None

    with pytest.raises(NotFoundError):
        asyncio.run(manager.logout("not-valid"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.logout(str(ObjectId())))


def test_refresh_tokens_rotates_and_rejects_invalid():
    manager, collection = _auth_manager()
    object_id = ObjectId()
    user_id = str(object_id)
    refresh_token, expires_at = manager.jwt_service.create_refresh_token(user_id=user_id, username="alice", role=UserRole.ADMIN)
    refresh_hash = manager.refresh_token_service.hash_token(refresh_token)
    user = UserModel(username="alice", password_hash=PasswordManager().hash_password(PASSWORD), role=UserRole.ADMIN, is_active=True, created_at=NOW, updated_at=NOW, refresh_token_hash=refresh_hash, refresh_token_expires_at=expires_at)
    document = user.model_dump(exclude={"id"})
    document["_id"] = object_id
    collection.documents.append(document)

    rotated = asyncio.run(manager.refresh_tokens(refresh_token))
    assert rotated.access_token
    assert rotated.refresh_token != refresh_token

    with pytest.raises(AuthenticationError):
        asyncio.run(manager.refresh_tokens("not-a-jwt"))
