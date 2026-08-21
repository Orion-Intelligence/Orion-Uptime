from fastapi import status

from app.service.constants import Messages


class AppException(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class AuthenticationError(AppException):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

class AuthorizationError(AppException):
    def __init__(self, message: str = Messages.ACCESS_DENIED):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )

class NotFoundError(AppException):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )

class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )

class ValidationError(AppException):
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

class RateLimitError(AppException):
    def __init__(self, message: str = Messages.TOO_MANY_LOGIN_ATTEMPTS):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
