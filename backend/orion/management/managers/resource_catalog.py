from __future__ import annotations

RESOURCE_TYPES: tuple[str, ...] = ("HTTP", "API", "ping", "heartbeat", "orion_script", "auth_profiles", "users", "status_pages", "slack_integrations", "email_integrations")
VIEWER_RESOURCE_TYPES = frozenset({"HTTP", "API", "ping", "heartbeat", "orion_script"})

KIND_RESOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "monitor": ("HTTP", "API", "ping", "heartbeat", "orion_script"),
    "auth_profile": ("auth_profiles",),
    "user": ("users",),
    "status_page": ("status_pages",),
    "slack_integration": ("slack_integrations",),
    "email_integration": ("email_integrations",),
}


def resource_types_for(kind: str) -> tuple[str, ...]:
    return KIND_RESOURCE_TYPES.get(kind, ())
