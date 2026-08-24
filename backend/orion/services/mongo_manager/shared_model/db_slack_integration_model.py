from datetime import datetime

from pydantic import BaseModel, Field

from orion.services.mongo_manager.shared_model.persisted_model import PersistedModel


class SlackIntegrationModel(PersistedModel):
    name: str
    name_key: str
    webhook_url: str
    monitor_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CreateSlackIntegrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    webhook_url: str = Field(min_length=1, max_length=500)
    monitor_ids: list[str] = Field(default_factory=list, max_length=1000)


class UpdateSlackIntegrationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    webhook_url: str | None = Field(default=None, min_length=1, max_length=500)
    monitor_ids: list[str] | None = Field(default=None, max_length=1000)


class SlackIntegrationSummaryResponse(BaseModel):
    id: str
    name: str
    monitor_ids: list[str]
    monitor_count: int
    created_at: datetime
    updated_at: datetime


class SlackIntegrationResponse(SlackIntegrationSummaryResponse):
    webhook_url: str
