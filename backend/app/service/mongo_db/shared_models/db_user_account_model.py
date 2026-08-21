from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.service.mongo_db.shared_models.persisted_model import PersistedModel


class UserRole(str, Enum):
    ADMIN = "admin"
    VIEWER = "viewer"

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"

@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str

class UserModel(PersistedModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    username: str
    password_hash: str
    role: UserRole
    refresh_token_hash: str | None = None
    refresh_token_expires_at: datetime | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"

class CurrentUserResponse(BaseModel):
    id: str
    username: str
    role: UserRole

class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)

class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=8)
    role: UserRole | None = None
    is_active: bool | None = None

class UserResponse(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool

    created_at: datetime
    updated_at: datetime
    last_login: datetime | None
