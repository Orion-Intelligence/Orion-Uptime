from fastapi import APIRouter, Depends, status

from orion.api.interactive.email_integration_manager.email_integration_manager import EmailIntegrationManager
from orion.management.managers.service_manager import ServiceManager
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.shared_model.db_email_integration_model import CreateEmailIntegrationRequest, EmailIntegrationResponse, UpdateEmailIntegrationRequest
from orion.shared_models.exceptions import ValidationError
from orion.shared_models.responses import SuccessResponse, success_response


def get_email_integration_service() -> EmailIntegrationManager:
    services = ServiceManager.get_instance().services
    if services is None:
        raise ValidationError("Email integration service is not available.")
    return services.email_integration_service


router = APIRouter(prefix="/integrations/email", tags=["Email Integrations"], dependencies=[Depends(require_admin())])


@router.post("", response_model=SuccessResponse[EmailIntegrationResponse], status_code=status.HTTP_201_CREATED)
async def create_integration(request: CreateEmailIntegrationRequest, service: EmailIntegrationManager = Depends(get_email_integration_service)):
    return success_response(message="Email integration created successfully.", data=await service.create_integration(request))


@router.get("", response_model=SuccessResponse[list[EmailIntegrationResponse]])
async def list_integrations(service: EmailIntegrationManager = Depends(get_email_integration_service)):
    return success_response(message="Email integrations retrieved successfully.", data=await service.list_integrations())


@router.get("/{integration_id}", response_model=SuccessResponse[EmailIntegrationResponse])
async def get_integration(integration_id: str, service: EmailIntegrationManager = Depends(get_email_integration_service)):
    return success_response(message="Email integration retrieved successfully.", data=await service.get_integration(integration_id))


@router.put("/{integration_id}", response_model=SuccessResponse[EmailIntegrationResponse])
async def update_integration(integration_id: str, request: UpdateEmailIntegrationRequest, service: EmailIntegrationManager = Depends(get_email_integration_service)):
    return success_response(message="Email integration updated successfully.", data=await service.update_integration(integration_id, request))


@router.delete("/{integration_id}", response_model=SuccessResponse[None])
async def delete_integration(integration_id: str, service: EmailIntegrationManager = Depends(get_email_integration_service)):
    await service.delete_integration(integration_id)
    return success_response(message="Email integration deleted successfully.", data=None)
