import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Messages:
    LOGIN_SUCCESS = "Login successful."
    LOGOUT_SUCCESS = "Logout successful."
    INVALID_REFRESH_TOKEN = "Invalid or expired refresh token."  # nosec B105
    INVALID_CREDENTIALS = "Invalid username or password."
    TOO_MANY_LOGIN_ATTEMPTS = "Too many failed login attempts. Try again in a few minutes."

    USER_NOT_FOUND = "User not found."
    USER_DISABLED = "User account is disabled."
    CURRENT_USER_RETRIEVED = "Current user retrieved successfully."
    NO_ACTIVE_SESSION = "No active session."
    ACCESS_DENIED = "You do not have permission to perform this action."
    USER_CREATED = "User created successfully."
    USER_UPDATED = "User updated successfully."
    USER_DELETED = "User deleted successfully."
    USERNAME_ALREADY_EXISTS = "Username already exists."
    USER_FETCHED = "User retrieved successfully."
    USERS_FETCHED = "Users retrieved successfully."

    ADMIN_PROMOTION_NOT_ALLOWED = "Users cannot be promoted to administrator."
    ADMIN_ROLE_CHANGE_NOT_ALLOWED = "Administrator role cannot be changed."
    ADMIN_DELETION_NOT_ALLOWED = "Administrator account cannot be deleted."

    MONITOR_ALREADY_EXISTS = "monitor already exists."
    MONITOR_NOT_FOUND = "monitor not found."
    MONITOR_FETCHED = "monitor fetched successfully."
    MONITOR_CREATED = "monitor created successfully."
    MONITOR_UPDATED = "monitor updated successfully."
    MONITOR_DELETED = "monitor deleted successfully."

    DASHBOARD_FETCHED = "Dashboard summary retrieved successfully."

    HEARTBEAT_RECEIVED = "Heartbeat received."


class Collections:
    USERS = "users"
    INCIDENTS = "incidents"
    MONITOR_RESULTS = "monitor_results"
    MONITOR_STATES = "monitor_states"
    HTTP_MONITORS = "http_monitors"
    API_MONITORS = "api_monitors"
    PING_MONITORS = "ping_monitors"
    HEARTBEAT_MONITORS = "heartbeat_monitors"
    ORION_SCRIPT_MONITORS = "orion_script_monitors"
    AUTH_PROFILES = "auth_profiles"
    STATUS_PAGES = "status_pages"
    SLACK_INTEGRATIONS = "slack_integrations"
    EMAIL_INTEGRATIONS = "email_integrations"


class OrionIntelligence:
    FEEDER_SCRIPTS_PATH = "/api/profile/feeder/scripts"
    FEEDER_ENTRY_TYPES = ("scripts", "values")
    FEEDER_PAGE_LIMIT = 1000
    FEEDER_MAX_PAGES = 10
    FEEDER_RESULT_SEPARATOR = ":"


class Limits:
    INTEGRATION_NAME_MAX_LENGTH = 100
    LOGIN_MAX_FAILURES_PER_ACCOUNT_AND_IP = 5
    LOGIN_MAX_FAILURES_PER_IP = 30
    LOGIN_MAX_FAILURES_PER_ACCOUNT = 50
    DEFAULT_FAILURE_THRESHOLD = 3
    RECOVERY_THRESHOLD = 1


class Intervals:
    REFRESH_REPLAY_SECONDS = 10
    TARGET_RESOLUTION_TIMEOUT_SECONDS = 10
    CHECK_DEADLINE_GRACE_SECONDS = 10
    RECONCILE_INTERVAL_SECONDS = 30
    SCHEDULER_STALL_SECONDS = 180
    ERROR_BACKOFF_SECONDS = 15
    WATCHDOG_INTERVAL_SECONDS = 30
    KEEP_ALIVE_SECONDS = 15
    PUBLIC_REFRESH_SECONDS = 60


class Cookies:
    ACCESS_TOKEN = "access_token"  # nosec B105
    REFRESH_TOKEN = "refresh_token"  # nosec B105
    AUTH_PATH = "/api"


class EnvVars:
    TRUSTED_PROXIES = "TRUSTED_PROXIES"
    ALLOW_PRIVATE_TARGETS = "MONITOR_ALLOW_PRIVATE_TARGETS"
    ENCRYPTION_KEY = "CREDENTIALS_ENCRYPTION_KEY"  # nosec B105


class AllowedValues:
    SMTP_SECURITY = {"none", "starttls", "ssl"}
    SLACK_WEBHOOK_HOSTS = {"hooks.slack.com", "hooks.slack-gov.com"}
    MONITOR_SCHEMES = {"http", "https"}


class Patterns:
    EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,63}$")


class HttpStatus:
    DESCRIPTION_FALLBACKS = {
        102: "The server received the request and is still processing it",
        103: "The server returned preliminary headers before the final response",
        207: "The response contains separate statuses for multiple operations",
        208: "The resource was already reported earlier in the same response",
        226: "The response represents the result of one or more instance manipulations",
        422: "The server understood the request but could not process its content",
        423: "The requested resource is locked",
        424: "The request failed because an operation it depended on also failed",
        425: "The server rejected the request because replaying it could be unsafe",
        426: "The server requires the client to switch to a different protocol",
        506: "The server has a circular content-negotiation configuration",
        507: "The server has insufficient storage to complete the request",
        508: "The server detected an infinite loop while processing the request",
        510: "The request requires additional extensions before it can be completed",
    }


class SecurityHeaders:
    CONTENT_SECURITY_POLICY = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "manifest-src 'self'",
            "media-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "worker-src 'self'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "require-trusted-types-for 'script'",
            "trusted-types angular angular#bundler",
            "upgrade-insecure-requests",
        ]
    )

    DEFAULTS = {"Content-Security-Policy": CONTENT_SECURITY_POLICY, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin", "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"}

    STRICT_TRANSPORT_SECURITY = "max-age=31536000; includeSubDomains"


class Paths:
    ANGULAR_BUILD = (BACKEND_DIR / "build").resolve()
