from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.auth_manager.auth_manager import PasswordManager
from orion.api.interactive.user_account_manager.user_account_manager import UserManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_user_account_model import UserRole
from orion.shared_models.exceptions import AuthorizationError, ConflictError, NotFoundError
from tests.fake_model.fakes import FakeCollection

PASSWORD = "password123"


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.USERS: collection})
    manager = UserManager(engine, PasswordManager())
    return manager, collection


def _create(manager, username="alice", password=PASSWORD):
    return asyncio.run(manager.create_user(username, password))


def test_create_user_persists_viewer_and_hashes_password():
    manager, collection = _manager()
    created = _create(manager)

    assert created.username == "alice"
    assert created.role == UserRole.VIEWER
    assert created.is_active is True
    document = collection.documents[0]
    assert document["password_hash"] != PASSWORD
    assert PasswordManager().verify_password(PASSWORD, document["password_hash"]) is True


def test_create_user_rejects_duplicate_username():
    manager, _ = _manager()
    _create(manager)
    with pytest.raises(ConflictError):
        _create(manager)


def test_get_user_returns_response():
    manager, _ = _manager()
    created = _create(manager)

    fetched = asyncio.run(manager.get_user(created.id))
    assert fetched.username == "alice"
    assert fetched.id == created.id


def test_get_user_raises_not_found_for_missing_or_invalid_id():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_user(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_user("not-a-valid-id"))


def test_list_users_returns_only_viewers():
    manager, _ = _manager()
    _create(manager, username="alice")
    _create(manager, username="bob")
    asyncio.run(manager.ensure_default_admin("admin", "adminpass1"))

    listed = asyncio.run(manager.list_users())
    assert {user.username for user in listed} == {"alice", "bob"}
    assert all(user.role == UserRole.VIEWER for user in listed)


def test_update_user_changes_username_password_and_active_flag():
    manager, collection = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_user(created.id, username="alice2", password="newpassword1", is_active=False))
    assert updated.username == "alice2"
    assert updated.is_active is False
    document = collection.documents[0]
    assert PasswordManager().verify_password("newpassword1", document["password_hash"]) is True


def test_update_user_with_no_changes_returns_current_user():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_user(created.id))
    assert updated.username == created.username
    assert updated.is_active == created.is_active


def test_update_user_rejects_duplicate_username():
    manager, _ = _manager()
    _create(manager, username="alice")
    bob = _create(manager, username="bob")

    with pytest.raises(ConflictError):
        asyncio.run(manager.update_user(bob.id, username="alice"))


def test_update_user_can_promote_role_without_renaming():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_user(created.id, role=UserRole.ADMIN))
    assert updated.role == UserRole.ADMIN


def test_update_user_rejects_promotion_to_admin_when_renaming():
    manager, _ = _manager()
    created = _create(manager)

    with pytest.raises(AuthorizationError):
        asyncio.run(manager.update_user(created.id, username="renamed", role=UserRole.ADMIN))


def test_update_user_rejects_changing_admin_role_away():
    manager, collection = _manager()
    asyncio.run(manager.ensure_default_admin("admin", "adminpass1"))
    admin_id = str(collection.documents[0]["_id"])

    with pytest.raises(AuthorizationError):
        asyncio.run(manager.update_user(admin_id, role=UserRole.VIEWER))


def test_update_user_raises_not_found_for_missing_user():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_user(str(ObjectId()), username="ghost"))


def test_delete_user_removes_viewer():
    manager, collection = _manager()
    created = _create(manager)

    asyncio.run(manager.delete_user(created.id))
    assert collection.documents == []


def test_delete_user_rejects_admin_deletion():
    manager, collection = _manager()
    asyncio.run(manager.ensure_default_admin("admin", "adminpass1"))
    admin_id = str(collection.documents[0]["_id"])

    with pytest.raises(AuthorizationError):
        asyncio.run(manager.delete_user(admin_id))
    assert len(collection.documents) == 1


def test_delete_user_raises_not_found_for_missing_user():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_user(str(ObjectId())))


def test_default_admin_password_in_use():
    manager, _ = _manager()
    asyncio.run(manager.ensure_default_admin("admin", "adminpass1"))

    assert asyncio.run(manager.default_admin_password_in_use("admin", "adminpass1")) is True
    assert asyncio.run(manager.default_admin_password_in_use("admin", "wrong-password")) is False
    assert asyncio.run(manager.default_admin_password_in_use("ghost", "adminpass1")) is False


def test_ensure_default_admin_creates_then_updates_existing():
    manager, collection = _manager()

    created = asyncio.run(manager.ensure_default_admin("admin", "adminpass1"))
    assert created is True
    assert collection.documents[0]["role"] == UserRole.ADMIN

    collection.documents[0]["is_active"] = False
    updated = asyncio.run(manager.ensure_default_admin("admin", "adminpass1"))
    assert updated is False
    assert collection.documents[0]["is_active"] is True
