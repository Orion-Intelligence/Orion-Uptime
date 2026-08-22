from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

from orion.api.interactive.auth_manager.auth_manager import PasswordManager
from orion.constants.constant import Collections, Messages
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_user_account_model import UserModel, UserResponse, UserRole
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import AuthorizationError, ConflictError, NotFoundError


class UserManager:
    def __init__(self, engine: AIOEngine, password_service: PasswordManager):
        self.collection = engine.database[Collections.USERS]
        self.password_service = password_service

    async def create_user(self, username: str, password: str) -> UserResponse:
        if await self.collection.find_one({"username": username}) is not None:
            raise ConflictError(Messages.USERNAME_ALREADY_EXISTS)

        now = datetime.now(UTC)
        user = UserModel(username=username, password_hash=self.password_service.hash_password(password), role=UserRole.VIEWER, is_active=True, refresh_token_hash=None, created_at=now, updated_at=now, last_login=None)
        document = user.model_dump()
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        user.id = str(result.inserted_id)
        realtime_broker.notify("user", user.id)
        return UserResponse(**user.model_dump())

    async def get_user_model(self, user_id: str) -> UserModel:
        try:
            object_id = ObjectId(user_id)
        except InvalidId as exc:
            raise NotFoundError(Messages.USER_NOT_FOUND) from exc

        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            raise NotFoundError(Messages.USER_NOT_FOUND)
        document = with_string_id(document)
        return UserModel(**document)

    async def list_user_models(self) -> list[UserModel]:
        cursor = self.collection.find({"role": UserRole.VIEWER}).sort("created_at", -1)
        users = []
        async for document in cursor:
            users.append(UserModel(**with_string_id(document)))
        return users

    async def get_user(self, user_id: str) -> UserResponse:
        return UserResponse(**(await self.get_user_model(user_id)).model_dump())

    async def list_users(self) -> list[UserResponse]:
        return [UserResponse(**user.model_dump()) for user in await self.list_user_models()]

    async def update_user(self, user_id: str, username: str | None = None, password: str | None = None, role: UserRole | None = None, is_active: bool | None = None) -> UserResponse:
        user = await self.get_user_model(user_id)
        update_data: dict[str, object] = {}

        if username is not None and username != user.username:
            existing = await self.collection.find_one({"username": username})
            if existing is not None:
                raise ConflictError(Messages.USERNAME_ALREADY_EXISTS)
            if role == UserRole.ADMIN:
                raise AuthorizationError(Messages.ADMIN_PROMOTION_NOT_ALLOWED)
            update_data["username"] = username

        if password is not None:
            update_data["password_hash"] = self.password_service.hash_password(password)

        if role is not None:
            if user.role == UserRole.ADMIN and role != UserRole.ADMIN:
                raise AuthorizationError(Messages.ADMIN_ROLE_CHANGE_NOT_ALLOWED)
            update_data["role"] = role

        if is_active is not None:
            update_data["is_active"] = is_active

        if update_data:
            update_data["updated_at"] = datetime.now(UTC)
            await self.collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})

        updated_user = await self.get_user_model(user_id)
        realtime_broker.notify("user", updated_user.id)
        return UserResponse(**updated_user.model_dump())

    async def delete_user(self, user_id: str) -> None:
        user = await self.get_user_model(user_id)
        if user.role == UserRole.ADMIN:
            raise AuthorizationError(Messages.ADMIN_DELETION_NOT_ALLOWED)
        await self.collection.delete_one({"_id": ObjectId(user_id)})
        realtime_broker.notify("user", user_id)

    async def default_admin_password_in_use(self, username: str, password: str) -> bool:
        document = await self.collection.find_one({"username": username}, {"password_hash": 1}) or {}  # nosec B105
        password_hash = document.get("password_hash")
        if not isinstance(password_hash, str):
            return False
        return self.password_service.verify_password(password=password, hashed_password=password_hash)

    async def ensure_default_admin(self, username: str, password: str) -> bool:
        now = datetime.now(UTC)
        existing = await self.collection.find_one({"username": username})
        if existing is not None:
            await self.collection.update_one({"username": username}, {"$set": {"role": UserRole.ADMIN, "is_active": True, "updated_at": now}})
            return False

        admin = UserModel(username=username, password_hash=self.password_service.hash_password(password), role=UserRole.ADMIN, refresh_token_hash=None, is_active=True, created_at=now, updated_at=now, last_login=None)
        document = admin.model_dump()
        document.pop("id", None)
        await self.collection.insert_one(document)
        return True
