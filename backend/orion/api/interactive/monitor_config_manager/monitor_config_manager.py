from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from bson import ObjectId

from orion.api.interactive.api_monitor_manager.api_monitor_manager import ApiMonitorManager
from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.api.interactive.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from orion.services.mongo_manager.shared_model.db_api_monitor_model import CreateApiMonitorRequest, UpdateApiMonitorRequest
from orion.services.mongo_manager.shared_model.db_monitor_config_model import ApiMonitorConfig, HeartbeatMonitorConfig, HttpMonitorConfig, MonitorConfigBase, MonitorConfigDocument, MonitorImportResult, PingMonitorConfig
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError, ValidationError


class MonitorConfigManager:
    def __init__(self, http_monitors: HttpMonitorManager, api_monitors: ApiMonitorManager, ping_monitors: PingMonitorManager, heartbeat_monitors: HeartbeatMonitorManager):
        self.http_monitors = http_monitors
        self.api_monitors = api_monitors
        self.ping_monitors = ping_monitors
        self.heartbeat_monitors = heartbeat_monitors

    async def export_monitor(self, monitor_type: MonitorType, monitor_id: str) -> MonitorConfigDocument:
        if monitor_type == MonitorType.HTTP:
            monitor = await self.http_monitors.get_monitor_model(monitor_id)
            if monitor is None:
                raise NotFoundError("HTTP monitor not found.")
            return HttpMonitorConfig(
                monitor_id=monitor.persisted_id,
                monitor_type=MonitorType.HTTP,
                name=monitor.name,
                url=monitor.url,
                check_interval=monitor.check_interval,
                timeout=monitor.timeout,
                expected_status_code=monitor.expected_status_code,
                expected_response_time_ms=monitor.expected_response_time_ms,
                is_active=monitor.is_active,
            )

        if monitor_type == MonitorType.API:
            monitor = await self.api_monitors.get_monitor_model(monitor_id)
            if monitor is None:
                raise NotFoundError("API monitor not found.")
            auth_profile_id = monitor.auth_profile_id
            auth_profile_name = None
            if auth_profile_id and self.api_monitors.auth_profile_service is not None:
                auth_profile = await self.api_monitors.auth_profile_service.get_profile_model(auth_profile_id)
                if auth_profile is not None:
                    auth_profile_id = None
                    auth_profile_name = auth_profile.name
            return ApiMonitorConfig(
                monitor_id=monitor.persisted_id,
                monitor_type=MonitorType.API,
                name=monitor.name,
                url=monitor.url,
                method=monitor.method,
                headers=monitor.headers,
                request_body=monitor.request_body,
                expected_status_code=monitor.expected_status_code,
                expected_json=monitor.expected_json,
                check_interval=monitor.check_interval,
                timeout=monitor.timeout,
                expected_response_time_ms=monitor.expected_response_time_ms,
                expected_headers=monitor.expected_headers,
                expected_content_type=monitor.expected_content_type,
                auth_profile_id=auth_profile_id,
                auth_profile_name=auth_profile_name,
                is_active=monitor.is_active,
            )

        if monitor_type == MonitorType.PING:
            monitor = await self.ping_monitors.get_monitor_model(monitor_id)
            if monitor is None:
                raise NotFoundError("Ping monitor not found.")
            return PingMonitorConfig(
                monitor_id=monitor.persisted_id,
                monitor_type=MonitorType.PING,
                name=monitor.name,
                host=monitor.host,
                check_interval=monitor.check_interval,
                timeout=monitor.timeout,
                expected_response_time_ms=monitor.expected_response_time_ms,
                is_active=monitor.is_active,
            )

        monitor = await self.heartbeat_monitors.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError("Heartbeat monitor not found.")
        return HeartbeatMonitorConfig(
            monitor_id=monitor.persisted_id,
            monitor_type=MonitorType.HEARTBEAT,
            name=monitor.name,
            expected_heartbeat_interval=monitor.expected_heartbeat_interval,
            grace_period=monitor.grace_period,
            is_active=monitor.is_active,
        )

    async def import_monitor(self, config: MonitorConfigDocument) -> MonitorImportResult:
        if isinstance(config, ApiMonitorConfig):
            config = await self._resolve_auth_profile(config)
        existing = await self._existing_monitor(config)
        if existing is not None:
            monitor_id = existing.persisted_id
            changes = self._changed_fields(config, existing)
            if changes:
                await self._update_monitor(monitor_id, config, changes)
            return MonitorImportResult(action="updated", monitor_id=monitor_id, monitor_type=config.monitor_type, name=config.name)

        monitor_id, heartbeat_token = await self._create_monitor(config)
        return MonitorImportResult(action="created", monitor_id=monitor_id, monitor_type=config.monitor_type, name=config.name, heartbeat_token=heartbeat_token)

    async def _existing_monitor(self, config: MonitorConfigDocument):
        if not config.monitor_id:
            return None
        if config.monitor_type == MonitorType.HTTP:
            return await self.http_monitors.get_monitor_model(config.monitor_id)
        if config.monitor_type == MonitorType.API:
            return await self.api_monitors.get_monitor_model(config.monitor_id)
        if config.monitor_type == MonitorType.PING:
            return await self.ping_monitors.get_monitor_model(config.monitor_id)
        return await self.heartbeat_monitors.get_monitor_model(config.monitor_id)

    async def _create_monitor(self, config: MonitorConfigDocument) -> tuple[str, str | None]:
        if isinstance(config, HttpMonitorConfig):
            created = await self.http_monitors.create_monitor(
                name=config.name,
                url=config.url,
                check_interval=config.check_interval,
                timeout=config.timeout,
                expected_status_code=config.expected_status_code,
                expected_response_time_ms=config.expected_response_time_ms,
            )
            if not config.is_active:
                await self._update_monitor(created.id, config, {"is_active": False})
            return created.id, None

        if isinstance(config, ApiMonitorConfig):
            request = CreateApiMonitorRequest(**self._configuration_fields(config))
            created = await self.api_monitors.create_monitor(request)
            if not config.is_active:
                await self._update_monitor(created.id, config, {"is_active": False})
            return created.id, None

        if isinstance(config, PingMonitorConfig):
            created = await self.ping_monitors.create_monitor(
                name=config.name,
                host=config.host,
                check_interval=config.check_interval,
                timeout=config.timeout,
                expected_response_time_ms=config.expected_response_time_ms,
            )
            if not config.is_active:
                await self._update_monitor(created.id, config, {"is_active": False})
            return created.id, None

        created = await self.heartbeat_monitors.create_monitor(
            name=config.name,
            expected_heartbeat_interval=config.expected_heartbeat_interval,
            grace_period=config.grace_period,
        )
        token_hash = hashlib.sha256(created.heartbeat_token.encode()).hexdigest()
        document = await self.heartbeat_monitors.collection.find_one({"heartbeat_token_hash": token_hash}, {"_id": 1})
        if document is None:
            raise RuntimeError("The imported heartbeat monitor could not be retrieved after creation.")
        monitor_id = str(document["_id"])
        if not config.is_active:
            await self._update_monitor(monitor_id, config, {"is_active": False})
        return monitor_id, created.heartbeat_token

    async def _update_monitor(self, monitor_id: str, config: MonitorConfigDocument, changes: dict | None = None) -> None:
        changes = changes or {
            **self._configuration_fields(config),
            "is_active": config.is_active,
        }
        if isinstance(config, HttpMonitorConfig):
            clear_expected_response_time = "expected_response_time_ms" in changes and changes["expected_response_time_ms"] is None
            if clear_expected_response_time:
                await self.http_monitors.collection.update_one(
                    {"_id": ObjectId(monitor_id)},
                    {"$set": {"expected_response_time_ms": None, "updated_at": datetime.now(UTC)}},
                )
            await self.http_monitors.update_monitor(
                http_monitor_id=monitor_id,
                name=changes.get("name"),
                url=changes.get("url"),
                check_interval=changes.get("check_interval"),
                timeout=changes.get("timeout"),
                expected_status_code=changes.get("expected_status_code"),
                expected_response_time_ms=changes.get("expected_response_time_ms"),
                is_active=changes.get("is_active"),
            )
            if clear_expected_response_time and len(changes) == 1:
                realtime_broker.notify("monitor", monitor_id)
            return

        if isinstance(config, ApiMonitorConfig):
            await self.api_monitors.update_monitor(monitor_id, UpdateApiMonitorRequest(**changes))
            return

        if isinstance(config, PingMonitorConfig):
            clear_expected_response_time = "expected_response_time_ms" in changes and changes["expected_response_time_ms"] is None
            if clear_expected_response_time:
                await self.ping_monitors.collection.update_one(
                    {"_id": ObjectId(monitor_id)},
                    {"$set": {"expected_response_time_ms": None, "updated_at": datetime.now(UTC)}},
                )
            await self.ping_monitors.update_monitor(
                monitor_id=monitor_id,
                name=changes.get("name"),
                host=changes.get("host"),
                check_interval=changes.get("check_interval"),
                timeout=changes.get("timeout"),
                expected_response_time_ms=changes.get("expected_response_time_ms"),
                is_active=changes.get("is_active"),
            )
            if clear_expected_response_time and len(changes) == 1:
                realtime_broker.notify("monitor", monitor_id)
            return

        await self.heartbeat_monitors.update_monitor(
            monitor_id,
            name=changes.get("name"),
            expected_heartbeat_interval=changes.get("expected_heartbeat_interval"),
            grace_period=changes.get("grace_period"),
            is_active=changes.get("is_active"),
        )

    @staticmethod
    def _configuration_fields(config: MonitorConfigBase) -> dict:
        return config.model_dump(exclude={"format", "version", "monitor_id", "monitor_type", "is_active", "auth_profile_name"})

    async def _resolve_auth_profile(self, config: ApiMonitorConfig) -> ApiMonitorConfig:
        requested_id = config.auth_profile_id
        requested_name = config.auth_profile_name
        if requested_name is None and requested_id is not None and not ObjectId.is_valid(requested_id):
            requested_name = requested_id
            requested_id = None
        if requested_name is None:
            return config

        auth_profile_service = self.api_monitors.auth_profile_service
        if auth_profile_service is None:
            raise ValidationError("Auth profile name resolution is unavailable.")
        auth_profile = await auth_profile_service.get_profile_model_by_name(requested_name)
        if auth_profile is None:
            raise NotFoundError(f'Auth profile "{requested_name}" was not found.')
        if requested_id is not None and requested_id != auth_profile.persisted_id:
            raise ValidationError("auth_profile_id and auth_profile_name refer to different auth profiles.")
        return config.model_copy(update={"auth_profile_id": auth_profile.persisted_id, "auth_profile_name": requested_name})

    @classmethod
    def _changed_fields(cls, config: MonitorConfigDocument, existing) -> dict:
        imported = {
            **cls._configuration_fields(config),
            "is_active": config.is_active,
        }
        return {
            field: value
            for field, value in imported.items()
            if getattr(existing, field) != value
        }
