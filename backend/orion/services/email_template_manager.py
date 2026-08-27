from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template, TemplateNotFound, select_autoescape

EMAIL_INTEGRATION_ALERT_TEMPLATE = "email_integration_alert.html"


class EmailTemplateManager:
    __instance: EmailTemplateManager | None = None

    @classmethod
    def get_instance(cls) -> EmailTemplateManager:
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance

    def __init__(self) -> None:
        self._environment: Environment | None = None
        self._templates: dict[str, Template] = {}

    @property
    def initialized(self) -> bool:
        return bool(self._templates)

    def initialize(self, search_paths: Iterable[Path] | None = None) -> None:
        if self.initialized:
            return

        paths = tuple(search_paths or self._default_search_paths())
        existing_paths = [path for path in paths if path.is_dir()]
        if not existing_paths:
            searched = ", ".join(str(path) for path in paths)
            raise RuntimeError(f"Email template directory was not found. Searched: {searched}")

        environment = Environment(
            loader=FileSystemLoader([str(path) for path in existing_paths]),
            autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=True),
            undefined=StrictUndefined,
            auto_reload=False,
            cache_size=-1,
        )
        try:
            template = environment.get_template(EMAIL_INTEGRATION_ALERT_TEMPLATE)
        except TemplateNotFound as exc:
            searched = ", ".join(str(path) for path in existing_paths)
            raise RuntimeError(f"Email template {EMAIL_INTEGRATION_ALERT_TEMPLATE!r} was not found in: {searched}") from exc

        self._environment = environment
        self._templates = {EMAIL_INTEGRATION_ALERT_TEMPLATE: template}

    def render(self, template_name: str, **context) -> str:
        template = self._templates.get(template_name)
        if template is None:
            raise RuntimeError("Email templates have not been initialized.")
        return template.render(**context)

    def clear(self) -> None:
        if self._environment is not None:
            self._environment.cache.clear()
        self._environment = None
        self._templates = {}

    @staticmethod
    def _default_search_paths() -> tuple[Path, Path]:
        backend_root = Path(__file__).resolve().parents[2]
        relative_path = Path("assets") / "html templates"
        return (
            backend_root.parent / "client" / "src" / relative_path,
            backend_root / "build" / relative_path,
        )
