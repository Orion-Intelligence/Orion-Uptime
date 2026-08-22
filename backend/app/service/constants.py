class Messages:
    LOGIN_SUCCESS = "Login successful."
    LOGOUT_SUCCESS = "Logout successful."
    INVALID_REFRESH_TOKEN = "Invalid or expired refresh token."  # nosec B105
    INVALID_CREDENTIALS = "Invalid username or password."
    TOO_MANY_LOGIN_ATTEMPTS = "Too many failed login attempts. Try again in a few minutes."

    USER_NOT_FOUND = "User not found."
    USER_DISABLED = "User account is disabled."
    CURRENT_USER_RETRIEVED = "Current user retrieved successfully."
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

    monitor_ALREADY_EXISTS = "monitor already exists."
    monitor_NOT_FOUND = "monitor not found."
    monitor_FETCHED = "monitor fetched successfully."
    monitor_CREATED = "monitor created successfully."
    monitor_UPDATED = "monitor updated successfully."
    monitor_DELETED = "monitor deleted successfully."

    DASHBOARD_FETCHED = "Dashboard summary retrieved successfully."

    heartbeat_RECEIVED = "Heartbeat received."

class Collections:
    USERS = "users"
    INCIDENTS = "incidents"
    MONITOR_RESULTS = "monitor_results"
    MONITOR_STATES = "monitor_states"
    HTTP_MONITORS = "http_monitors"
    API_MONITORS = "api_monitors"
    PING_MONITORS = "ping_monitors"
    HEARTBEAT_MONITORS = "heartbeat_monitors"
    AUTH_PROFILES = "auth_profiles"
    STATUS_PAGES = "status_pages"
