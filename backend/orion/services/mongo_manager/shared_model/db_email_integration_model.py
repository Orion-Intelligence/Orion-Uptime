from datetime import datetime

from pydantic import BaseModel, Field

from orion.services.mongo_manager.shared_model.persisted_model import PersistedModel


class EmailIntegrationModel(PersistedModel):
    name: str
    name_key: str
    email: str
    monitor_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CreateEmailIntegrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    monitor_ids: list[str] = Field(default_factory=list, max_length=1000)


class UpdateEmailIntegrationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    monitor_ids: list[str] | None = Field(default=None, max_length=1000)


class EmailIntegrationResponse(BaseModel):
    id: str
    name: str
    email: str
    monitor_ids: list[str]
    monitor_count: int
    created_at: datetime
    updated_at: datetime
