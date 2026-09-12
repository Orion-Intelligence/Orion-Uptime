from __future__ import annotations

import pytest

from orion.services.email_template_manager import EmailTemplateManager


@pytest.fixture(autouse=True)
def initialized_email_templates():
    template_manager = EmailTemplateManager.get_instance()
    template_manager.clear()
    template_manager.initialize()
    yield
    template_manager.clear()
