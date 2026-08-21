from fastapi import APIRouter, Depends, Request, Response
from jwt import PyJWTError

from app.core.client_ip import client_ip
from app.modules.auth_manager.auth_manager import AuthManager, login_throttle, revoked_access_tokens
from app.service.authorization import (
    ACCESS_TOKEN_COOKIE,
    clear_auth_cookies,
    get_auth_service,
    require_viewer,
    set_auth_cookies,
)
from app.service.constants import Messages
from app.service.exceptions import AuthenticationError
from app.service.mongo_db.shared_models.db_user_account_model import CurrentUserResponse, LoginRequest
from app.service.responses import SuccessResponse, success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=SuccessResponse[None])
async def login(request: LoginRequest, http_request: Request, response: Response, service: AuthManager = Depends(get_auth_service)):
    address = client_ip(http_request)
    login_throttle.check(address, request.username)
    try:
        data = await service.login(
            username=request.username,
            password=request.password,
        )
    except AuthenticationError:
        login_throttle.record_failure(address, request.username)
        raise
    login_throttle.record_success(address, request.username)
    set_auth_cookies(response, data)

    return success_response(
        message=Messages.LOGIN_SUCCESS,
        data=None,
    )

@router.get("/me", response_model=SuccessResponse[CurrentUserResponse])
async def me(current_user: CurrentUserResponse = Depends(require_viewer())):
    return success_response(
        message=Messages.CURRENT_USER_RETRIEVED,
        data=current_user,
    )

@router.post("/logout", response_model=SuccessResponse[None],)
async def logout(http_request: Request, response: Response, current_user: CurrentUserResponse = Depends(require_viewer()), service: AuthManager = Depends(get_auth_service)):
    await service.logout(current_user.id)
    access_token = http_request.cookies.get(ACCESS_TOKEN_COOKIE)
    if access_token is not None:
        try:
            payload = service.jwt_service.verify_access_token(access_token)
        except PyJWTError:
            payload = None
        if payload is not None and payload.get("jti"):
            revoked_access_tokens.revoke(payload["jti"], float(payload["exp"]))
    clear_auth_cookies(response)

    return success_response(
        message=Messages.LOGOUT_SUCCESS,
        data=None,
    )
