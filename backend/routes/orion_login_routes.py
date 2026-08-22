from fastapi import APIRouter, Depends, status
from odmantic import AIOEngine

from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileResponse, CreateAuthProfileRequest, UpdateAuthProfileRequest
from orion.shared_models.responses import ApiResponse


def get_auth_profile_service(engine: AIOEngine = Depends(get_engine)) -> AuthProfileManager:
    return AuthProfileManager(engine)


router = APIRouter(prefix="/auth-profiles", tags=["Auth Profiles"], dependencies=[Depends(require_admin())])


@router.post("/create", response_model=ApiResponse[AuthProfileResponse], status_code=status.HTTP_201_CREATED)
async def create_profile(request: CreateAuthProfileRequest, service: AuthProfileManager = Depends(get_auth_profile_service)):
    profile = await service.create_profile(request)
    status_text = f"HTTP {profile.login_status_code}" if profile.login_status_code is not None else "no HTTP status"
    return ApiResponse(success=True, message=f"Login returned {status_text}. Auth profile created successfully.", data=profile)


@router.get("/list_all", response_model=ApiResponse[list[AuthProfileResponse]])
async def list_profiles(service: AuthProfileManager = Depends(get_auth_profile_service)):
    return ApiResponse(success=True, message="Auth profiles retrieved successfully.", data=await service.list_profiles())


@router.get("/{profile_id}", response_model=ApiResponse[AuthProfileResponse])
async def get_profile(profile_id: str, service: AuthProfileManager = Depends(get_auth_profile_service)):
    return ApiResponse(success=True, message="Auth profile retrieved successfully.", data=await service.get_profile(profile_id))


@router.put("/{profile_id}", response_model=ApiResponse[AuthProfileResponse])
async def update_profile(profile_id: str, request: UpdateAuthProfileRequest, service: AuthProfileManager = Depends(get_auth_profile_service)):
    return ApiResponse(success=True, message="Auth profile updated successfully.", data=await service.update_profile(profile_id, request))


@router.delete("/{profile_id}", response_model=ApiResponse[None])
async def delete_profile(profile_id: str, service: AuthProfileManager = Depends(get_auth_profile_service)):
    await service.delete_profile(profile_id)
    return ApiResponse(success=True, message="Auth profile deleted successfully.")
