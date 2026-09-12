from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from bson import ObjectId

from configs.app_dependency import AppDependency
from orion.api.interactive.auth_manager.auth_manager import AuthManager, PasswordManager, RefreshTokenManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_user_account_model import UserModel, UserRole
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)
PASSWORD = "password123"


def _auth_manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.USERS: collection})
    manager = AuthManager(engine=engine, password_manager=PasswordManager(), jwt_service=AppDependency(), refresh_token_manager=RefreshTokenManager())
    return manager, collection


def _store_user(collection, *, is_active=True, password=PASSWORD, refresh_hash=None, refresh_expires=None):
    object_id = ObjectId()
    user = UserModel(username="alice", password_hash=PasswordManager().hash_password(password), role=UserRole.ADMIN, is_active=is_active, created_at=NOW, updated_at=NOW, refresh_token_hash=refresh_hash, refresh_token_expires_at=refresh_expires)
    document = user.model_dump(exclude={"id"})
    document["_id"] = object_id
    collection.documents.append(document)
    return str(object_id)
