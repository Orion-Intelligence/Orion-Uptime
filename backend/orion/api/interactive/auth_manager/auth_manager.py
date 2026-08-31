from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from bson import ObjectId
from bson.errors import InvalidId
from jwt import PyJWTError
from odmantic import AIOEngine

from configs.app_dependency import AppDependency
from orion.constants.constant import Collections, Intervals, Limits, Messages
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_user_account_model import AuthTokens, CurrentUserResponse, TokenResponse, UserModel
from orion.shared_models.exceptions import AuthenticationError, NotFoundError, RateLimitError

LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60


@dataclass(frozen=True)
class RefreshReplay:
    tokens: AuthTokens
    rotated_token_hash: str
    expires_at: float


class PasswordManager:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password: str, hashed_password: str) -> bool:
        try:
            return self._hasher.verify(hashed_password, password)
        except (VerifyMismatchError, VerificationError):
            return False


class RefreshTokenManager:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()
        self._locks: dict[str, asyncio.Lock] = {}
        self._replays: dict[str, RefreshReplay] = {}

    def hash_token(self, token: str) -> str:
        return self._hasher.hash(token)

    def verify_token(self, token: str, hashed_token: str) -> bool:
        try:
            return self._hasher.verify(hashed_token, token)
        except (VerifyMismatchError, VerificationError):
            return False

    def lock_for(self, user_id: str) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    def get_replay(self, token: str) -> RefreshReplay | None:
        key = self._token_key(token)
        replay = self._replays.get(key)
        if replay is None:
            return None
        if time.monotonic() >= replay.expires_at:
            self._replays.pop(key, None)
            return None
        return replay

    def remember_rotation(self, old_token: str, tokens: AuthTokens, rotated_token_hash: str) -> None:
        now = time.monotonic()
        self._replays = {key: replay for key, replay in self._replays.items() if replay.expires_at > now}
        self._replays[self._token_key(old_token)] = RefreshReplay(tokens=tokens, rotated_token_hash=rotated_token_hash, expires_at=now + Intervals.REFRESH_REPLAY_SECONDS)

    @staticmethod
    def _token_key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class LoginThrottle:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def check(self, client_ip: str, username: str) -> None:
        now = self.clock()
        self._prune(now)
        for key in self._keys(client_ip, username):
            if self._locked_until.get(key, 0.0) > now:
                raise RateLimitError

    def record_failure(self, client_ip: str, username: str) -> None:
        now = self.clock()
        self._prune(now)
        limits = (Limits.LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP, Limits.LOGIN_MAX_FAILURES_PER_IP, Limits.LOGIN_MAX_FAILURES_PER_ACCOUNT)
        for key, limit in zip(self._keys(client_ip, username), limits, strict=True):
            attempts = self._failures.setdefault(key, [])
            attempts.append(now)
            if len(attempts) >= limit:
                self._locked_until[key] = now + LOGIN_LOCKOUT_SECONDS
                self._failures.pop(key, None)

    def record_success(self, client_ip: str, username: str) -> None:
        pair_key, _, account_key = self._keys(client_ip, username)
        for key in (pair_key, account_key):
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    @staticmethod
    def _keys(client_ip: str, username: str) -> tuple[str, str, str]:
        account = username.strip().lower()
        return f"pair:{client_ip}:{account}", f"ip:{client_ip}", f"account:{account}"

    def _prune(self, now: float) -> None:
        cutoff = now - LOGIN_FAILURE_WINDOW_SECONDS
        for key in list(self._failures):
            recent = [attempt for attempt in self._failures[key] if attempt > cutoff]
            if recent:
                self._failures[key] = recent
            else:
                del self._failures[key]
        for key in [key for key, until in self._locked_until.items() if until <= now]:
            del self._locked_until[key]


class RevokedAccessTokens:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._revoked: dict[str, float] = {}

    def revoke(self, token_id: str, expires_at: float) -> None:
        self._prune()
        self._revoked[token_id] = expires_at

    def is_revoked(self, token_id: str | None) -> bool:
        if token_id is None:
            return False
        self._prune()
        return token_id in self._revoked

    def _prune(self) -> None:
        now = self.clock()
        for token_id in [token_id for token_id, expires_at in self._revoked.items() if expires_at <= now]:
            del self._revoked[token_id]


password_service = PasswordManager()
refresh_token_service = RefreshTokenManager()
login_throttle = LoginThrottle()
revoked_access_tokens = RevokedAccessTokens()


class AuthManager:
    def __init__(self, engine: AIOEngine, password_manager: PasswordManager, jwt_service: AppDependency, refresh_token_manager: RefreshTokenManager) -> None:
        self.collection = engine.database[Collections.USERS]
        self.password_service = password_manager
        self.jwt_service = jwt_service
        self.refresh_token_service = refresh_token_manager

    async def login(self, username: str, password: str) -> TokenResponse:
        document = await self.collection.find_one({"username": username})
        if document is None:
            raise AuthenticationError(Messages.INVALID_CREDENTIALS)

        user = UserModel(**with_string_id(document))
        if user.id is None or not self.password_service.verify_password(password=password, hashed_password=user.password_hash):
            raise AuthenticationError(Messages.INVALID_CREDENTIALS)
        if not user.is_active:
            raise AuthenticationError(Messages.USER_DISABLED)

        refresh_token, refresh_token_expires_at = self.jwt_service.create_refresh_token(user_id=user.id, username=user.username, role=user.role)
        refresh_token_hash = self.refresh_token_service.hash_token(refresh_token)
        now = datetime.now(UTC)
        updated = await self.collection.update_one({"_id": ObjectId(user.id)}, {"$set": {"refresh_token_hash": refresh_token_hash, "refresh_token_expires_at": refresh_token_expires_at, "last_login": now, "updated_at": now}})
        if updated.matched_count == 0:
            raise NotFoundError(Messages.USER_NOT_FOUND)

        access_token = self.jwt_service.create_access_token(user_id=user.id, username=user.username, role=user.role)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh_tokens(self, refresh_token: str) -> AuthTokens:
        try:
            payload = self.jwt_service.verify_refresh_token(refresh_token)
        except PyJWTError as exc:
            raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN) from exc

        user_id = payload.get("sub")
        if not isinstance(user_id, str):
            raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN)
        try:
            object_id = ObjectId(user_id)
        except InvalidId as exc:
            raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN) from exc

        async with self.refresh_token_service.lock_for(user_id):
            replay = self.refresh_token_service.get_replay(refresh_token)
            if replay is not None:
                current_rotation = await self.collection.find_one({"_id": object_id, "is_active": True, "refresh_token_hash": replay.rotated_token_hash})
                if current_rotation is not None:
                    return replay.tokens

            document = await self.collection.find_one({"_id": object_id})
            if document is None:
                raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN)
            user = UserModel(**with_string_id(document))
            if user.id is None or not user.is_active or user.refresh_token_hash is None or user.refresh_token_expires_at is None:
                raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN)

            refresh_token_expires_at = user.refresh_token_expires_at
            if refresh_token_expires_at.tzinfo is None:
                refresh_token_expires_at = refresh_token_expires_at.replace(tzinfo=UTC)
            if refresh_token_expires_at <= datetime.now(UTC):
                raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN)
            if not self.refresh_token_service.verify_token(refresh_token, user.refresh_token_hash):
                raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN)

            new_refresh_token, new_refresh_token_expires_at = self.jwt_service.create_refresh_token(user_id=user.id, username=user.username, role=user.role)
            new_refresh_token_hash = self.refresh_token_service.hash_token(new_refresh_token)
            rotated = await self.collection.update_one({"_id": object_id, "refresh_token_hash": user.refresh_token_hash}, {"$set": {"refresh_token_hash": new_refresh_token_hash, "refresh_token_expires_at": new_refresh_token_expires_at, "updated_at": datetime.now(UTC)}})
            if rotated.modified_count == 0:
                raise AuthenticationError(Messages.INVALID_REFRESH_TOKEN)

            tokens = AuthTokens(access_token=self.jwt_service.create_access_token(user_id=user.id, username=user.username, role=user.role), refresh_token=new_refresh_token)
            self.refresh_token_service.remember_rotation(refresh_token, tokens, new_refresh_token_hash)
            return tokens

    async def get_current_user(self, user_id: str) -> CurrentUserResponse:
        try:
            object_id = ObjectId(user_id)
        except InvalidId as exc:
            raise NotFoundError(Messages.USER_NOT_FOUND) from exc

        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            raise NotFoundError(Messages.USER_NOT_FOUND)
        user = UserModel(**with_string_id(document))
        if not user.is_active:
            raise AuthenticationError(Messages.USER_DISABLED)
        return CurrentUserResponse(id=user.persisted_id, username=user.username, role=user.role)

    async def logout(self, user_id: str) -> None:
        try:
            object_id = ObjectId(user_id)
        except InvalidId as exc:
            raise NotFoundError(Messages.USER_NOT_FOUND) from exc

        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            raise NotFoundError(Messages.USER_NOT_FOUND)

        result = await self.collection.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "refresh_token_hash": None,  # nosec B105
                    "refresh_token_expires_at": None,  # nosec B105
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        if result.matched_count == 0:
            raise NotFoundError(Messages.USER_NOT_FOUND)
