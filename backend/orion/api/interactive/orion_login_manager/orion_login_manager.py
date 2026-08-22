from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
from orion.constants.constant import Collections
from orion.services.encryption_manager.secrets import secret_box
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel, AuthProfileResponse, CreateAuthProfileRequest, UpdateAuthProfileRequest
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import ConflictError, NotFoundError, ValidationError


class AuthProfileManager:
    DEPRECATED_FIELDS: ClassVar[dict[str, str]] = {
        "credential_location": "",
        "token_field": "",  # nosec B105
        "expires_in_field": "",
    }

    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.AUTH_PROFILES]

    async def create_profile(self, request: CreateAuthProfileRequest) -> AuthProfileResponse:
        if await self.collection.find_one({"name": request.name}) is not None:
            raise ConflictError("An auth profile with this name already exists.")

        now = datetime.now(UTC)
        profile = AuthProfileModel(**request.model_dump(), method="POST", created_at=now, updated_at=now)

        token_manager = auth_token_state.token_manager
        if token_manager is None:
            raise ValidationError("Authentication service is not available.")
        try:
            token, login_status_code = await token_manager.authenticate_profile(profile)
        except auth_token_state.AuthTokenError as exc:
            raise ValidationError(str(exc)) from exc

        document = self._serialize(profile)
        result = await self.collection.insert_one(document)
        profile.id = str(result.inserted_id)
        token_manager.cache_token(profile.id, token)
        realtime_broker.notify("auth_profile", profile.id)
        return AuthProfileResponse(id=profile.id, name=profile.name, login_url=profile.login_url, method=profile.method, credential_fields=sorted(profile.credentials), created_at=profile.created_at, updated_at=profile.updated_at, login_status_code=login_status_code)

    async def get_profile_model(self, profile_id: str) -> AuthProfileModel | None:
        try:
            object_id = ObjectId(profile_id)
        except (InvalidId, TypeError):
            return None

        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        return self._deserialize(document)

    async def list_profile_models(self) -> list[AuthProfileModel]:
        profiles = []
        async for document in self.collection.find().sort("created_at", -1):
            profiles.append(self._deserialize(document))
        return profiles

    async def get_profile(self, profile_id: str) -> AuthProfileResponse:
        profile = await self.get_profile_model(profile_id)
        if profile is None:
            raise NotFoundError("Auth profile not found.")
        return AuthProfileResponse(id=profile.persisted_id, name=profile.name, login_url=profile.login_url, method=profile.method, credential_fields=sorted(profile.credentials), created_at=profile.created_at, updated_at=profile.updated_at)

    async def list_profiles(self) -> list[AuthProfileResponse]:
        profiles = await self.list_profile_models()
        return [AuthProfileResponse(id=profile.persisted_id, name=profile.name, login_url=profile.login_url, method=profile.method, credential_fields=sorted(profile.credentials), created_at=profile.created_at, updated_at=profile.updated_at) for profile in profiles]

    async def update_profile(self, profile_id: str, request: UpdateAuthProfileRequest) -> AuthProfileResponse:
        profile = await self.get_profile_model(profile_id)
        if profile is None:
            raise NotFoundError("Auth profile not found.")

        update_data = request.model_dump(exclude_unset=True)
        required_fields = {"name", "login_url", "credentials"}
        invalid_null_fields = [field for field in required_fields if field in update_data and update_data[field] is None]
        if invalid_null_fields:
            raise ValidationError(f"Auth profile fields cannot be null: {', '.join(sorted(invalid_null_fields))}.")
        if update_data.get("headers") is None and "headers" in update_data:
            update_data["headers"] = {}

        if "name" in update_data and await self.collection.find_one({"name": update_data["name"], "_id": {"$ne": ObjectId(profile_id)}}) is not None:
            raise ConflictError("An auth profile with this name already exists.")
        if update_data.get("credentials") is not None:
            update_data["credentials_encrypted"] = secret_box.encrypt_mapping(update_data.pop("credentials"))
        update_data["updated_at"] = datetime.now(UTC)
        await self.collection.update_one({"_id": ObjectId(profile_id)}, {"$set": update_data, "$unset": {**self.DEPRECATED_FIELDS, "credentials": ""}})
        self._invalidate_token(profile_id)
        updated = await self.get_profile_model(profile_id)
        if updated is None:
            raise NotFoundError("Auth profile not found.")
        realtime_broker.notify("auth_profile", updated.id)
        return AuthProfileResponse(id=updated.persisted_id, name=updated.name, login_url=updated.login_url, method=updated.method, credential_fields=sorted(updated.credentials), created_at=updated.created_at, updated_at=updated.updated_at)

    async def delete_profile(self, profile_id: str) -> None:
        try:
            object_id = ObjectId(profile_id)
        except (InvalidId, TypeError):
            raise NotFoundError("Auth profile not found.") from None

        result = await self.collection.delete_one({"_id": object_id})
        deleted = result.deleted_count > 0
        if not deleted:
            raise NotFoundError("Auth profile not found.")
        self._invalidate_token(profile_id)
        realtime_broker.notify("auth_profile", profile_id)

    async def create_indexes(self) -> None:
        await self.collection.update_many({}, {"$set": {"method": "POST"}, "$unset": self.DEPRECATED_FIELDS})
        await self._encrypt_plaintext_credentials()
        await self.collection.create_index("name", unique=True)

    async def _encrypt_plaintext_credentials(self) -> None:
        async for document in self.collection.find({"credentials": {"$exists": True}}, {"credentials": 1}):
            await self.collection.update_one({"_id": document["_id"]}, {"$set": {"credentials_encrypted": secret_box.encrypt_mapping(document["credentials"] or {})}, "$unset": {"credentials": ""}})

    @staticmethod
    def _serialize(profile: AuthProfileModel) -> dict:
        document = profile.model_dump(exclude={"id", "credentials"})
        document["credentials_encrypted"] = secret_box.encrypt_mapping(profile.credentials)
        return document

    @staticmethod
    def _deserialize(document: dict) -> AuthProfileModel:
        document = with_string_id(document)
        encrypted = document.pop("credentials_encrypted", None)
        if encrypted is not None:
            document["credentials"] = secret_box.decrypt_mapping(encrypted)
        return AuthProfileModel(**document)

    @staticmethod
    def _invalidate_token(profile_id: str) -> None:
        if auth_token_state.token_manager is not None:
            auth_token_state.token_manager.invalidate(profile_id)
