from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager
from orion.management.jobs.monitoring_controller.checkers.api_checker import ApiChecker
from orion.management.jobs.monitoring_controller.checkers.heartbeat_checker import HeartbeatChecker
from orion.management.jobs.monitoring_controller.checkers.http_checker import HTTPChecker
from orion.management.jobs.monitoring_controller.checkers.ping_checker import PingChecker
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType


class CheckerFactory:
    def __init__(self, token_manager: AccessTokenCookieManager | None = None):
        self._api_checker = ApiChecker(token_manager=token_manager)
        self._checkers = {MonitorType.HTTP: HTTPChecker(), MonitorType.API: self._api_checker, MonitorType.PING: PingChecker(), MonitorType.HEARTBEAT: HeartbeatChecker()}

    def get_checker(self, monitor_type: MonitorType):
        try:
            return self._checkers[monitor_type]
        except KeyError:
            raise ValueError(f"Unsupported monitor type: {monitor_type}") from None

    async def close(self):
        for checker in self._checkers.values():
            await checker.close()
        if token_manager := self._api_checker.token_manager:
            await token_manager.close()
