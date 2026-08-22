from fastapi import APIRouter, Depends
from odmantic import AIOEngine

from orion.api.interactive.auth_manager.auth_manager import password_service
from orion.api.interactive.user_account_manager.user_account_manager import UserManager
from orion.constants.constant import Messages
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_user_account_model import CreateUserRequest, UpdateUserRequest, UserResponse
from orion.shared_models.responses import SuccessResponse, success_response


def get_user_service(engine: AIOEngine = Depends(get_engine)) -> UserManager:
    return UserManager(engine, password_service)


router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_admin())])


@router.post("/create", response_model=SuccessResponse[UserResponse])
async def create_user(request: CreateUserRequest, service: UserManager = Depends(get_user_service)):
    return success_response(message=Messages.USER_CREATED, data=await service.create_user(username=request.username, password=request.password))


@router.get("/list", response_model=SuccessResponse[list[UserResponse]])
async def list_users(service: UserManager = Depends(get_user_service)):
    return success_response(message=Messages.USERS_FETCHED, data=await service.list_users())


@router.get("/{user_id}/get_one", response_model=SuccessResponse[UserResponse])
async def get_user(user_id: str, service: UserManager = Depends(get_user_service)):
    return success_response(message=Messages.USER_FETCHED, data=await service.get_user(user_id))


@router.put("/{user_id}/update", response_model=SuccessResponse[UserResponse])
async def update_user(user_id: str, request: UpdateUserRequest, service: UserManager = Depends(get_user_service)):
    return success_response(message=Messages.USER_UPDATED, data=await service.update_user(user_id=user_id, username=request.username, password=request.password, role=request.role, is_active=request.is_active))


@router.delete("/{user_id}/delete", response_model=SuccessResponse[None])
async def delete_user(user_id: str, service: UserManager = Depends(get_user_service)):
    await service.delete_user(user_id)

    return success_response(message=Messages.USER_DELETED, data=None)
