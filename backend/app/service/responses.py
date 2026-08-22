from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: T

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: list[str] = Field(default_factory=list)

def success_response(message: str, data: Any = None) -> SuccessResponse:
    return SuccessResponse(
        message=message,
        data=data,
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
