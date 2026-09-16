from __future__ import annotations

from orion.management.managers import resource_catalog


def test_resource_types_for_maps_notify_kinds():
    assert resource_catalog.resource_types_for("monitor") == ("HTTP", "API", "ping", "heartbeat", "orion_script")
    assert resource_catalog.resource_types_for("user") == ("users",)
    assert resource_catalog.resource_types_for("status_page") == ("status_pages",)
    assert resource_catalog.resource_types_for("slack_integration") == ("slack_integrations",)
    assert resource_catalog.resource_types_for("email_integration") == ("email_integrations",)
    assert resource_catalog.resource_types_for("auth_profile") == ("auth_profiles",)


def test_unknown_kind_invalidates_nothing():
    assert resource_catalog.resource_types_for("unknown") == ()


def test_every_mapped_type_is_a_known_resource_type():
    mapped = {resource_type for types in resource_catalog.KIND_RESOURCE_TYPES.values() for resource_type in types}
    assert mapped == set(resource_catalog.RESOURCE_TYPES)


def test_viewer_resource_types_cover_monitors_only():
    assert set(resource_catalog.VIEWER_RESOURCE_TYPES) == set(resource_catalog.KIND_RESOURCE_TYPES["monitor"])
