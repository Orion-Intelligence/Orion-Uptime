from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from bson import ObjectId

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.constants.constant import Collections
from orion.services.encryption_manager.secrets import secret_box
from orion.services.mongo_manager.shared_model.db_orion_login_model import CreateAuthProfileRequest, UpdateAuthProfileRequest
from orion.shared_models.exceptions import ConflictError, NotFoundError, ValidationError
from tests.fake_model.fakes import FakeCollection

NOW = datetime.now(UTC)
DEFAULT_CREDENTIALS = {"username": "admin", "password": "secret"}


@pytest.fixture(autouse=True)
def auth_crypto(monkeypatch):
    monkeypatch.setattr(secret_box, "encrypt_mapping", lambda values: json.dumps(values))
    monkeypatch.setattr(secret_box, "decrypt_mapping", json.loads)


def _fake_token_manager(*, token="token-1", status_code=200, error=None):
    calls = {"authenticate": [], "cache": [], "invalidate": []}

    async def authenticate_profile(profile):
        calls["authenticate"].append(profile)
        if error is not None:
            raise error
        return token, status_code

    def cache_token(profile_id, cached_token):
        calls["cache"].append((profile_id, cached_token))

    def invalidate(profile_id):
        calls["invalidate"].append(profile_id)

    manager = SimpleNamespace(authenticate_profile=authenticate_profile, cache_token=cache_token, invalidate=invalidate)
    return manager, calls


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.AUTH_PROFILES: collection})
    return AuthProfileManager(engine), collection


def _create_request(name="Profile", login_url="https://example.com/login", credentials=None, headers=None):
    return CreateAuthProfileRequest(name=name, login_url=login_url, credentials=credentials or DEFAULT_CREDENTIALS, headers=headers or {})


def _seed_profile(manager, monkeypatch, *, name="Profile", login_url="https://example.com/login", credentials=None):
    fake_token_manager, _ = _fake_token_manager()
    monkeypatch.setattr(auth_token_state, "token_manager", fake_token_manager)
    return asyncio.run(manager.create_profile(_create_request(name=name, login_url=login_url, credentials=credentials)))


def test_create_profile_success_caches_token_and_returns_response(monkeypatch):
    manager, collection = _manager()
    fake_token_manager, calls = _fake_token_manager(token="tok-abc", status_code=200)
    monkeypatch.setattr(auth_token_state, "token_manager", fake_token_manager)

    response = asyncio.run(manager.create_profile(_create_request(name="Primary")))

    assert response.name == "Primary"
    assert response.method == "POST"
    assert response.login_status_code == 200
    assert response.credential_fields == ["password", "username"]
    assert response.is_log_source is False
    assert calls["cache"] == [(response.id, "tok-abc")]
    assert collection.documents[0]["name"] == "Primary"


def test_create_profile_rejects_duplicate_name(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="Primary")

    with pytest.raises(ConflictError):
        asyncio.run(manager.create_profile(_create_request(name="Primary", login_url="https://example.com/other")))


def test_create_profile_rejects_duplicate_credentials_for_same_login_url(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="First")

    with pytest.raises(ConflictError):
        asyncio.run(manager.create_profile(_create_request(name="Second")))


def test_create_profile_allows_same_credentials_for_different_login_url(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="First", login_url="https://example.com/a", credentials={"username": "same", "password": "same"})

    second = _seed_profile(manager, monkeypatch, name="Second", login_url="https://example.com/b", credentials={"username": "same", "password": "same"})
    assert second.name == "Second"


def test_create_profile_allows_different_credentials_for_same_login_url(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="First", login_url="https://example.com/shared", credentials={"username": "a", "password": "b"})

    second = _seed_profile(manager, monkeypatch, name="Second", login_url="https://example.com/shared", credentials={"username": "c", "password": "d"})
    assert second.name == "Second"


def test_create_profile_requires_token_manager(monkeypatch):
    manager, _ = _manager()
    monkeypatch.setattr(auth_token_state, "token_manager", None)

    with pytest.raises(ValidationError):
        asyncio.run(manager.create_profile(_create_request()))


def test_create_profile_wraps_auth_token_error(monkeypatch):
    manager, _ = _manager()
    fake_token_manager, _ = _fake_token_manager(error=auth_token_state.AuthTokenError("boom", status_code=401))
    monkeypatch.setattr(auth_token_state, "token_manager", fake_token_manager)

    with pytest.raises(ValidationError):
        asyncio.run(manager.create_profile(_create_request()))


def test_get_profile_model_returns_none_for_missing_or_invalid():
    manager, _ = _manager()
    assert asyncio.run(manager.get_profile_model(str(ObjectId()))) is None
    assert asyncio.run(manager.get_profile_model("not-an-object-id")) is None


def test_get_profile_model_returns_model(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)

    model = asyncio.run(manager.get_profile_model(created.id))
    assert model.name == "Profile"
    assert model.credentials == DEFAULT_CREDENTIALS


def test_get_profile_model_handles_legacy_document_without_encrypted_credentials():
    manager, collection = _manager()
    object_id = ObjectId()
    collection.documents.append({"_id": object_id, "name": "Legacy", "login_url": "https://example.com/legacy", "method": "POST", "headers": {}, "is_log_source": False, "created_at": NOW, "updated_at": NOW})

    model = asyncio.run(manager.get_profile_model(str(object_id)))
    assert model.credentials == {}


def test_get_profile_model_by_name(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch, name="ByName")

    found = asyncio.run(manager.get_profile_model_by_name("ByName"))
    assert found.id == created.id
    assert asyncio.run(manager.get_profile_model_by_name("missing")) is None


def test_list_profile_models_returns_all(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="One", login_url="https://example.com/one")
    _seed_profile(manager, monkeypatch, name="Two", login_url="https://example.com/two")

    models = asyncio.run(manager.list_profile_models())
    assert {model.name for model in models} == {"One", "Two"}


def test_get_profile_returns_response_with_credentials(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)

    fetched = asyncio.run(manager.get_profile(created.id))
    assert fetched.credentials == DEFAULT_CREDENTIALS
    assert fetched.credential_fields == ["password", "username"]


def test_get_profile_missing_or_invalid_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_profile(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_profile("not-valid"))


def test_list_profiles_excludes_credentials(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="One")

    listed = asyncio.run(manager.list_profiles())
    assert [profile.name for profile in listed] == ["One"]
    assert listed[0].credentials is None


def test_update_profile_changes_name_and_headers(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch, name="Old")

    updated = asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(name="New", headers={"X-A": "1"})))
    assert updated.name == "New"
    assert updated.headers == {"X-A": "1"}


def test_update_profile_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_profile(str(ObjectId()), UpdateAuthProfileRequest(name="x")))


def test_update_profile_rejects_null_required_fields(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)

    with pytest.raises(ValidationError):
        asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(name=None)))
    with pytest.raises(ValidationError):
        asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(login_url=None)))
    with pytest.raises(ValidationError):
        asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(credentials=None)))


def test_update_profile_headers_none_becomes_empty_dict(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)
    asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(headers={"X": "1"})))

    updated = asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(headers=None)))
    assert updated.headers == {}


def test_update_profile_rejects_duplicate_name(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="First", login_url="https://example.com/a")
    second = _seed_profile(manager, monkeypatch, name="Second", login_url="https://example.com/b")

    with pytest.raises(ConflictError):
        asyncio.run(manager.update_profile(second.id, UpdateAuthProfileRequest(name="First")))


def test_update_profile_rejects_duplicate_credentials(monkeypatch):
    manager, _ = _manager()
    _seed_profile(manager, monkeypatch, name="First", login_url="https://example.com/login", credentials={"username": "a", "password": "b"})
    second = _seed_profile(manager, monkeypatch, name="Second", login_url="https://example.com/other", credentials={"username": "c", "password": "d"})

    with pytest.raises(ConflictError):
        asyncio.run(manager.update_profile(second.id, UpdateAuthProfileRequest(login_url="https://example.com/login", credentials={"username": "a", "password": "b"})))


def test_update_profile_encrypts_new_credentials_and_invalidates_token(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)
    fake_token_manager, calls = _fake_token_manager()
    monkeypatch.setattr(auth_token_state, "token_manager", fake_token_manager)

    updated = asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(credentials={"username": "new", "password": "new-pass"})))

    assert updated.credential_fields == ["password", "username"]
    assert calls["invalidate"] == [created.id]
    stored = asyncio.run(manager.get_profile(created.id))
    assert stored.credentials == {"username": "new", "password": "new-pass"}


def test_update_profile_skips_invalidate_when_token_manager_unset(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)
    monkeypatch.setattr(auth_token_state, "token_manager", None)

    updated = asyncio.run(manager.update_profile(created.id, UpdateAuthProfileRequest(name="Renamed")))
    assert updated.name == "Renamed"


def test_select_log_source_marks_only_target_and_returns_profile(monkeypatch):
    manager, _ = _manager()
    first = _seed_profile(manager, monkeypatch, name="First", login_url="https://example.com/a")
    second = _seed_profile(manager, monkeypatch, name="Second", login_url="https://example.com/b")
    asyncio.run(manager.select_log_source(first.id))

    result = asyncio.run(manager.select_log_source(second.id))
    assert result.is_log_source is True

    other = asyncio.run(manager.get_profile(first.id))
    assert other.is_log_source is False


def test_select_log_source_missing_or_invalid_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.select_log_source("not-valid"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.select_log_source(str(ObjectId())))


def test_clear_log_source_resets_flag(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)
    asyncio.run(manager.select_log_source(created.id))

    asyncio.run(manager.clear_log_source())

    result = asyncio.run(manager.get_profile(created.id))
    assert result.is_log_source is False


def test_get_log_source_profile_returns_model_or_none(monkeypatch):
    manager, _ = _manager()
    created = _seed_profile(manager, monkeypatch)
    assert asyncio.run(manager.get_log_source_profile()) is None

    asyncio.run(manager.select_log_source(created.id))
    log_source = asyncio.run(manager.get_log_source_profile())
    assert log_source.id == created.id


def test_delete_profile_removes_document_and_invalidates_token(monkeypatch):
    manager, collection = _manager()
    created = _seed_profile(manager, monkeypatch)
    fake_token_manager, calls = _fake_token_manager()
    monkeypatch.setattr(auth_token_state, "token_manager", fake_token_manager)

    asyncio.run(manager.delete_profile(created.id))

    assert collection.documents == []
    assert calls["invalidate"] == [created.id]


def test_delete_profile_missing_or_invalid_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_profile("not-valid"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_profile(str(ObjectId())))


def test_create_indexes_normalizes_method(monkeypatch):
    manager, collection = _manager()
    _seed_profile(manager, monkeypatch)
    collection.documents[0]["method"] = "GET"

    asyncio.run(manager.create_indexes())

    assert collection.documents[0]["method"] == "POST"


def test_comparable_login_url_normalizes_trailing_slash_and_whitespace():
    assert AuthProfileManager._comparable_login_url(" https://example.com/login/ ") == "https://example.com/login"
