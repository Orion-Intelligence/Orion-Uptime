export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

type UserRole = 'admin' | 'viewer';

export interface CurrentUser {
  id: string;
  username: string;
  role: UserRole;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface CreateUserRequest {
  username: string;
  password: string;
}

export interface UserResponse extends CurrentUser {
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login: string | null;
}

export interface DashboardSummary {
  total_monitors: number;
  active_monitors: number;
  inactive_monitors: number;
  monitors_up: number;
  monitors_down: number;
  monitors_unknown: number;
  slow_monitors: number;
  open_incidents: number;
  average_response_time_ms: number;
  overall_uptime_percentage: number;
}

export interface AuthProfileOption {
  id: string;
  name: string;
}

export interface DashboardIncident {
  id: string;
  monitor_id: string;
  monitor_name: string;
  started_at: string;
  resolved_at: string | null;
  duration_seconds: number | null;
  reason: string;
  status_code: number | null;
}

export interface DashboardActivity {
  monitor_id: string;
  monitor_name: string;
  status: 'up' | 'down' | 'unknown';
  status_code: number | null;
  response_time_ms: number | null;
  is_slow: boolean;
  checked_at: string;
}

export interface ResourceRecord {
  id: string;
  name: string;
  monitor_type?: string;
  status?: string;
  is_active?: boolean;
  url?: string;
  host?: string;
  login_url?: string;
  method?: string;
  expected_json?: Record<string, unknown> | null;
  credential_fields?: string[];
  check_interval?: number;
  timeout?: number;
  expected_response_time_ms?: number | null;
  expected_heartbeat_interval?: number;
  last_checked_at?: string | null;
  last_heartbeat_at?: string | null;
  created_at?: string;
}

export type MonitorConfigType = 'HTTP' | 'API' | 'ping' | 'heartbeat';

export interface MonitorConfigDocument {
  format: 'orion-monitor-config';
  version: 1;
  monitor_id?: string | null;
  monitor_type: MonitorConfigType;
  name: string;
  is_active: boolean;
  [key: string]: unknown;
}

export interface MonitorImportResult {
  action: 'created' | 'updated';
  monitor_id: string;
  monitor_type: MonitorConfigType;
  name: string;
  heartbeat_token: string | null;
}

export interface MonitorOverview {
  id: string;
  name: string;
  monitor_type: string;
  status: 'up' | 'down' | 'unknown';
  is_active: boolean;
  created_at: string;
  last_checked_at: string | null;
  uptime_percentage: number | null;
  current_uptime_seconds: number;
  latest_downtime_seconds: number;
  measurement_seconds: number;
  downtime_seconds: number;
  snapshot_at: string;
}

export interface StatusPage {
  id: string;
  name: string;
  slug: string;
  description: string;
  monitor_ids: string[];
  monitor_count: number;
  public_path: string;
  created_at: string;
  updated_at: string;
}

export interface SlackIntegration {
  id: string;
  name: string;
  monitor_ids: string[];
  monitor_count: number;
  created_at: string;
  updated_at: string;
}

export interface SlackIntegrationDetail extends SlackIntegration {
  webhook_url: string;
}

export interface EmailIntegration {
  id: string;
  name: string;
  email: string;
  monitor_ids: string[];
  monitor_count: number;
  created_at: string;
  updated_at: string;
}

export interface PublicStatusPage {
  name: string;
  slug: string;
  description: string;
  overall_status: 'operational' | 'degraded' | 'outage' | 'unknown';
  monitor_count: number;
  monitors_up: number;
  monitors_down: number;
  monitors_unknown: number;
  monitors_paused: number;
  generated_at: string;
  refresh_interval_seconds: number;
  uptime_status: PublicUptimeStatus;
  monitors: PublicStatusMonitor[];
}

export interface DailyUptime {
  date: string;
  uptime_percentage: number | null;
}

export interface PublicStatusMonitor extends MonitorOverview {
  uptime_90_days: number | null;
  daily_uptime: DailyUptime[];
}

export interface PublicUptimeStatus {
  last_24_hours: number | null;
  last_7_days: number | null;
  last_30_days: number | null;
  last_90_days: number | null;
}

export interface PublicResponseTimePoint {
  checked_at: string;
  response_time_ms: number;
}

export interface PublicResponseTimeMetrics {
  average_ms: number | null;
  maximum_ms: number | null;
  minimum_ms: number | null;
}

export interface PublicMonitorEvent {
  event_id: string;
  event_type: 'created' | 'down' | 'up';
  occurred_at: string;
  message: string;
  status_code: number | null;
  reason: string | null;
  duration_seconds: number | null;
  ongoing: boolean;
}

export interface PublicMonitorDetail {
  page_name: string;
  page_slug: string;
  generated_at: string;
  refresh_interval_seconds: number;
  monitor: PublicStatusMonitor;
  uptime_status: PublicUptimeStatus;
  response_time_points: PublicResponseTimePoint[];
  response_time_metrics: PublicResponseTimeMetrics;
  recent_events: PublicMonitorEvent[];
}

export interface MonitorIncident {
  id: string;
  status: 'open' | 'resolved';
  reason: string;
  status_code: number | null;
  started_at: string;
  resolved_at: string | null;
  duration_seconds: number;
}

export interface MonitorDetail extends MonitorOverview {
  incidents: MonitorIncident[];
}

export interface StatusHistoryPoint {
  checked_at: string;
  status: 'up' | 'down' | 'unknown';
}

export interface StatusHistory {
  monitor_id: string;
  history: StatusHistoryPoint[];
}

export interface ResponseHistoryPoint {
  checked_at: string;
  response_time_ms: number | null;
}

export interface ResponseHistory {
  monitor_id: string;
  points: ResponseHistoryPoint[];
}

export interface RealtimeResources {
  HTTP: ResourceRecord[];
  API: ResourceRecord[];
  ping: ResourceRecord[];
  heartbeat: ResourceRecord[];
  auth_profiles: ResourceRecord[];
  users: UserResponse[];
  status_pages: StatusPage[];
  slack_integrations: SlackIntegration[];
  email_integrations: EmailIntegration[];
}

export interface RealtimeSnapshot {
  revision: number;
  generated_at: string;
  summary: DashboardSummary;
  incidents: DashboardIncident[];
  activity: DashboardActivity[];
  overviews: MonitorOverview[];
  changed_monitor_details: Partial<Record<string, MonitorDetail>>;
  resources?: RealtimeResources;
}

export interface ApiErrorBody {
  message?: string;
  detail?: string | Array<{ msg?: string }>;
}

export interface IntegrationSummary {
  id: string;
  name: string;
  monitor_ids: string[];
}

export interface IntegrationBody {
  name: string;
  monitor_ids: string[];
}

export interface ChartPoint<T> {
  data: T;
  x: number;
  y: number;
}
