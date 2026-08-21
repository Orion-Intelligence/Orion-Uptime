from datetime import datetime

from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus, MonitorType
from app.service.mongo_db.shared_models.persisted_model import PersistedModel


class MonitorResultModel(PersistedModel):
    monitor_id: str
    monitor_type: MonitorType
    status: MonitorStatus
    status_code: int | None = None
    response_time_ms: int | None = None
    success: bool
    is_slow: bool = False
    checked_at: datetime
