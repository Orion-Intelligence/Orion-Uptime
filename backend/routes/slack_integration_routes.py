from fastapi import APIRouter, Depends, status

from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.management.managers.service_manager import ServiceManager
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.shared_model.db_slack_integration_model import CreateSlackIntegrationRequest, SlackIntegrationResponse, SlackIntegrationSummaryResponse, UpdateSlackIntegrationRequest
from orion.shared_models.exceptions import ValidationError
from orion.shared_models.responses import SuccessResponse, success_response


def get_slack_integration_service() -> SlackIntegrationManager:
    services = ServiceManager.get_instance().services
    if services is None:
        raise ValidationError("Slack integration service is not available.")
    return services.slack_integration_service


router = APIRouter(prefix="/integrations/slack", tags=["Slack Integrations"], dependencies=[Depends(require_admin())])


@router.post("", response_model=SuccessResponse[SlackIntegrationResponse], status_code=status.HTTP_201_CREATED)
async def create_integration(request: CreateSlackIntegrationRequest, service: SlackIntegrationManager = Depends(get_slack_integration_service)):
    return success_response(message="Slack integration created successfully.", data=await service.create_integration(request))


@router.get("", response_model=SuccessResponse[list[SlackIntegrationSummaryResponse]])
async def list_integrations(service: SlackIntegrationManager = Depends(get_slack_integration_service)):
    return success_response(message="Slack integrations retrieved successfully.", data=await service.list_integrations())


@router.get("/{integration_id}", response_model=SuccessResponse[SlackIntegrationResponse])
async def get_integration(integration_id: str, service: SlackIntegrationManager = Depends(get_slack_integration_service)):
    return success_response(message="Slack integration retrieved successfully.", data=await service.get_integration(integration_id))


@router.put("/{integration_id}", response_model=SuccessResponse[SlackIntegrationResponse])
async def update_integration(integration_id: str, request: UpdateSlackIntegrationRequest, service: SlackIntegrationManager = Depends(get_slack_integration_service)):
    return success_response(message="Slack integration updated successfully.", data=await service.update_integration(integration_id, request))


@router.delete("/{integration_id}", response_model=SuccessResponse[None])
async def delete_integration(integration_id: str, service: SlackIntegrationManager = Depends(get_slack_integration_service)):
    await service.delete_integration(integration_id)
    return success_response(message="Slack integration deleted successfully.", data=None)
