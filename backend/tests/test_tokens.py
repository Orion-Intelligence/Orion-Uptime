import jwt
import pytest
from jwt import PyJWTError

from app.core.app_dependency import AppDependency
from app.modules.auth_manager.auth_manager import RevokedAccessTokens
from app.service.mongo_db.shared_models.db_user_account_model import UserRole


def test_access_and_refresh_tokens_are_typed():
    service = AppDependency()
    access = service.create_access_token("507f1f77bcf86cd799439011", "admin", UserRole.ADMIN)
    refresh, _ = service.create_refresh_token("507f1f77bcf86cd799439011", "admin", UserRole.ADMIN)
    assert service.verify_access_token(access)["jti"]
    with pytest.raises(PyJWTError):
        service.verify_access_token(refresh)
    with pytest.raises(PyJWTError):
        service.verify_refresh_token(access)


def test_algorithm_is_pinned():
    service = AppDependency()
    access = service.create_access_token("507f1f77bcf86cd799439011", "admin", UserRole.ADMIN)
    payload = jwt.decode(access, options={"verify_signature": False})
    forged = jwt.encode(payload, "", algorithm="none")
    with pytest.raises(PyJWTError):
        service.verify_access_token(forged)


def test_revocation_store_expires_entries():
    clock = {"now": 100.0}
    store = RevokedAccessTokens(clock=lambda: clock["now"])
    store.revoke("abc", expires_at=200.0)
    assert store.is_revoked("abc")
    assert not store.is_revoked(None)
    clock["now"] = 201.0
    assert not store.is_revoked("abc")
