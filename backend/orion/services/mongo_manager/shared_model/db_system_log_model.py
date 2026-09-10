from pydantic import BaseModel, Field


class SystemLogEntry(BaseModel):
    type: str = ""
    time: str = ""
    file: str = ""
    source: str = ""
    message: str = ""


class SystemLogPageResponse(BaseModel):
    logs: list[SystemLogEntry] = Field(default_factory=list)
    page: int = 1
    limit: int = 25
    total: int | None = None
    has_more: bool = False
    source_profile_name: str | None = None
