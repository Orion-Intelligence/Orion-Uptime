import os
from collections.abc import Callable

from dotenv import load_dotenv
from fastapi import Depends, Request, Response
from jwt import PyJWTError
from odmantic import AIOEngine

from configs.app_dependency import app_dependency
from orion.api.interactive.auth_manager.auth_manager import AuthManager, password_service, refresh_token_service, revoked_access_tokens
from orion.constants.constant import Cookies, Messages
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_user_account_model import AuthTokens, CurrentUserResponse, TokenResponse, UserRole
from orion.shared_models.exceptions import AuthenticationError, AuthorizationError



def get_auth_service(engine: AIOEngine = Depends(get_engine)) -> AuthManager:
    return AuthManager(engine=engine, password_manager=password_service, jwt_service=app_dependency, refresh_token_manager=refresh_token_service)


def development_environment() -> bool:
    load_dotenv()
    return os.getenv("APP_ENV", "production").lower() in {"development", "local", "test"}


def _cookie_secure() -> bool:
    return not development_environment()


def set_auth_cookies(response: Response, tokens: AuthTokens | TokenResponse) -> None:
    load_dotenv()
    secure = _cookie_secure()
    response.set_cookie(key=Cookies.ACCESS_TOKEN, value=tokens.access_token, max_age=int(os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]) * 60, path=Cookies.AUTH_PATH, secure=secure, httponly=True, samesite="lax")
    response.set_cookie(key=Cookies.REFRESH_TOKEN, value=tokens.refresh_token, max_age=int(os.environ["REFRESH_TOKEN_EXPIRE_DAYS"]) * 24 * 60 * 60, path=Cookies.AUTH_PATH, secure=secure, httponly=True, samesite="lax")


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(Cookies.ACCESS_TOKEN, path=Cookies.AUTH_PATH, secure=_cookie_secure(), httponly=True, samesite="lax")
    response.delete_cookie(Cookies.REFRESH_TOKEN, path=Cookies.AUTH_PATH, secure=_cookie_secure(), httponly=True, samesite="lax")


async def get_current_user(request: Request, response: Response, service: AuthManager = Depends(get_auth_service)) -> CurrentUserResponse:
    payload = None
    cookie_access_token = request.cookies.get(Cookies.ACCESS_TOKEN)
    if cookie_access_token is not None:
        try:
            candidate = service.jwt_service.verify_access_token(cookie_access_token)
            if not revoked_access_tokens.is_revoked(candidate.get("jti")):
                payload = candidate
        except PyJWTError:
            payload = None

    if payload is None:
        refresh_token = request.cookies.get(Cookies.REFRESH_TOKEN)
        if refresh_token is None:
            raise AuthenticationError(Messages.INVALID_CREDENTIALS)
        tokens = await service.refresh_tokens(refresh_token)
        set_auth_cookies(response, tokens)
        response.headers["X-Access-Token-Refreshed"] = "true"
        payload = service.jwt_service.verify_access_token(tokens.access_token)

    return await service.get_current_user(payload["sub"])


def require_roles(*allowed_roles: UserRole) -> Callable:
    async def dependency(current_user: CurrentUserResponse = Depends(get_current_user)) -> CurrentUserResponse:
        if current_user.role not in allowed_roles:
            raise AuthorizationError
        return current_user

    return dependency


def require_admin() -> Callable:
    return require_roles(UserRole.ADMIN)


def require_viewer() -> Callable:
    return require_roles(UserRole.ADMIN, UserRole.VIEWER)
