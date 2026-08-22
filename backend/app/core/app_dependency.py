import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from dotenv import load_dotenv
from jwt import PyJWTError

from app.service.mongo_db.shared_models.db_user_account_model import TokenType, UserRole


def jwt_signing_key() -> str:
    return os.environ["JWT_SECRET"]


class AppDependency:
    def create_access_token(self, user_id: str, username: str, role: UserRole) -> str:
        load_dotenv()
        expire = datetime.now(UTC) + timedelta(minutes=int(os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]))
        payload = {
            "sub": user_id,
            "username": username,
            "role": role.value,
            "type": TokenType.ACCESS.value,
            "exp": expire,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(payload, jwt_signing_key(), algorithm=os.environ["JWT_ALGORITHM"])

    def create_refresh_token(self, user_id: str, username: str, role: UserRole) -> tuple[str, datetime]:
        load_dotenv()
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(days=int(os.environ["REFRESH_TOKEN_EXPIRE_DAYS"]))
        payload = {
            "sub": user_id,
            "username": username,
            "role": role.value,
            "type": TokenType.REFRESH.value,
            "iat": issued_at,
            "exp": expires_at,
            "jti": uuid.uuid4().hex,
        }
        token = jwt.encode(payload, jwt_signing_key(), algorithm=os.environ["JWT_ALGORITHM"])
        return token, expires_at

    def decode_token(self, token: str) -> dict[str, Any]:
        load_dotenv()
        return jwt.decode(token, jwt_signing_key(), algorithms=[os.environ["JWT_ALGORITHM"]])

    def verify_access_token(self, token: str) -> dict[str, Any]:
        payload = self.decode_token(token)
        if payload.get("type") != TokenType.ACCESS.value:
            raise PyJWTError("Invalid token type.")
        return payload

    def verify_refresh_token(self, token: str) -> dict[str, Any]:
        payload = self.decode_token(token)
        if payload.get("type") != TokenType.REFRESH.value:
            raise PyJWTError("Invalid token type.")
        return payload

app_dependency = AppDependency()
