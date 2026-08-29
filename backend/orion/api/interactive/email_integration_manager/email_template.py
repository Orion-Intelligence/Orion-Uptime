from __future__ import annotations

from html import escape
from string import Template

from orion.constants.constant import MailTemplates
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType


class AlertEmailTemplate:
    _markup: Template | None = None

    @classmethod
    def render(cls, *, monitor_name: str, monitor_type: MonitorType, is_down: bool, root_cause: str, status_code: int | None, response_time_ms: int | float | None, incident_started: str, resolved: str) -> str:
        state = "DOWN" if is_down else "RECOVERED"
        heading = "Monitor is down" if is_down else "Monitor recovered"
        summary = "Orion detected an availability incident that needs attention." if is_down else "Orion confirmed that the monitor is responding again."
        badge = "Incident open" if is_down else "Incident resolved"
        accent = "#f97066" if is_down else "#34d399"
        status_background = "#fff2f0" if is_down else "#effbf6"
        status_color = "#b42318" if is_down else "#16825f"
        icon = "!" if is_down else "&#10003;"
        details = [
            ("Monitor", monitor_name),
            ("State", state),
            ("Type", monitor_type.value),
        ]
        if monitor_type in (MonitorType.HTTP, MonitorType.API):
            details.append(("Status code", str(status_code) if status_code is not None else "No response"))
        if response_time_ms is not None:
            details.append(("Response time", f"{response_time_ms} ms"))
        details.extend([("Incident started", incident_started), ("Resolved", resolved)])
        detail_rows = "".join(
            f'<tr><td class="detail-label text-slate-500" style="width:42%;padding:12px 16px;border-bottom:1px solid #e3ebf3;color:#5f738f;font-size:12px;font-weight:500;vertical-align:top;">{escape(label)}</td><td class="detail-value text-slate-900" style="padding:12px 16px;border-bottom:1px solid #e3ebf3;color:#142033;font-size:13px;font-weight:600;line-height:1.5;vertical-align:top;word-break:break-word;">{escape(value)}</td></tr>'
            for label, value in details
        )

        return cls._template().substitute(
            preheader=escape(f"{monitor_name} is {state}"),
            status_border="#fecaca" if is_down else "#bbf7d0",
            status_background=status_background,
            accent=accent,
            icon=icon,
            badge_background="#fee2e2" if is_down else "#dcfce7",
            status_color=status_color,
            badge=badge,
            heading=heading,
            summary=summary,
            detail_rows=detail_rows,
            root_cause=escape(root_cause),
        )

    @classmethod
    def _template(cls) -> Template:
        if cls._markup is None:
            for directory in MailTemplates.DIRECTORIES:
                candidate = directory / MailTemplates.ALERT
                if candidate.is_file():
                    cls._markup = Template(candidate.read_text(encoding="utf-8"))
                    return cls._markup
            raise RuntimeError(f"{MailTemplates.ALERT} was not found in {[str(directory) for directory in MailTemplates.DIRECTORIES]}")
        return cls._markup
