from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

class Metadata(BaseModel):
    page: int | None = None
    page_size: int | None = None
    total_records: int | None = None
    total_pages: int | None = None

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: T
    metadata: Metadata | None = None

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: list[str] = Field(default_factory=list)
    metadata: Metadata | None = None

def success_response(message: str, data: Any = None, metadata: Metadata | None = None) -> SuccessResponse:
    return SuccessResponse(
        message=message,
        data=data,
        metadata=metadata,
    )

def error_response(message: str, errors: list[str] | None = None) -> ErrorResponse:
    return ErrorResponse(
        message=message,
        errors=errors or [],
    )

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: T | None = None
