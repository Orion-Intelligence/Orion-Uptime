from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.service.mongo_db.shared_models.persisted_model import PersistedModel


class AuthProfileModel(PersistedModel):
    name: str
    login_url: str
    method: Literal["POST"] = "POST"
    credentials: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

class CreateAuthProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    login_url: str = Field(min_length=1, max_length=500)
    credentials: dict[str, str] = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)

class UpdateAuthProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    login_url: str | None = Field(default=None, min_length=1, max_length=500)
    credentials: dict[str, str] | None = Field(default=None, min_length=1)
    headers: dict[str, str] | None = None

class AuthProfileResponse(BaseModel):
    id: str
    name: str
    login_url: str
    method: str
    credential_fields: list[str]
    created_at: datetime
    updated_at: datetime
    login_status_code: int | None = None
