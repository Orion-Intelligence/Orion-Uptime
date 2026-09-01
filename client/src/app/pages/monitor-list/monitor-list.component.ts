import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { AuthService } from '../../services/authentication/auth.service';
import { MonitorOverview, RealtimeResources, ResourceRecord } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NoticePageBase } from '../../shared/base/notice-page.base';
import { durationText } from '../../shared/utils/duration.util';
import { HEARTBEAT_NOTICE_MS, NOTICE_VISIBLE_MS } from '../../shared/constants/ui.constants';

@Component({
  selector: 'app-resource-list-page',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './monitor-list.component.html',
})
export class MonitorListComponent extends NoticePageBase {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly realtime = inject(RealtimeService);
  private readonly resourceType = signal<keyof RealtimeResources | null>(null);

  readonly title = signal('Resources');
  readonly description = signal('');
  readonly newUrl = signal('');
  readonly detailBase = signal('');
  readonly deletePath = signal('');
  readonly updatePath = signal('');
  readonly records = signal<ResourceRecord[]>([]);
  readonly overviews = signal<Partial<Record<string, MonitorOverview>>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly updatingId = signal('');
  readonly editingId = signal('');
  readonly editName = signal('');
  readonly editExpectedJson = signal('');
  readonly renamingId = signal('');
  readonly error = signal('');
  readonly heartbeatToken = signal('');
  readonly canManage = computed(() => this.auth.user()?.role === 'admin');
  readonly isMonitorList = computed(() => {
    const resourceType = this.resourceType();
    return resourceType !== null && this.isMonitorResource(resourceType);
  });
  readonly monitorSummary = computed(() => {
    const summary = { total: this.records().length, up: 0, down: 0, paused: 0, unknown: 0 };
    const overviews = this.overviews();
    for (const record of this.records()) {
      const overview = overviews[record.id];
      if (!overview) {
        summary.unknown += 1;
      }
      else if (!overview.is_active) {
        summary.paused += 1;
      }
      else {
        summary[overview.status] += 1;
      }
    }
    return summary;
  });

  constructor() {
    super();
    const navigationState = this.navigationState();
    const initialMessage = String(navigationState?.['message'] ?? '');
    const initialToken = String(navigationState?.['heartbeatToken'] ?? '');
    if (initialMessage || initialToken) {
      this.showHeartbeatNotice(initialMessage, initialToken);
    }
    this.realtime.connect();
    effect(() => {
      const error = this.realtime.error();
      if (error && this.loading()) {
        this.error.set(error);
      }
    });

    this.route.data.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((data) => {
      this.title.set(String(data['title'] ?? 'Resources'));
      this.description.set(String(data['description'] ?? ''));
      this.newUrl.set(String(data['newUrl'] ?? ''));
      this.detailBase.set(String(data['detailBase'] ?? ''));
      this.deletePath.set(String(data['deletePath'] ?? ''));
      this.updatePath.set(String(data['updatePath'] ?? ''));
      this.resourceType.set(data['resourceType'] as keyof RealtimeResources);
    });

    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      const resourceType = this.resourceType();
      if (!resourceType) {
        return;
      }
      const resources = this.resourcesOf(snapshot.resources, resourceType);
      if (resources) {
        this.records.set(resources as ResourceRecord[]);
      }
      else if (this.isMonitorResource(resourceType)) {
        this.records.set(snapshot.overviews
          .filter((overview) => overview.monitor_type === resourceType)
          .map((overview) => ({
            id: overview.id,
            name: overview.name,
            monitor_type: overview.monitor_type,
            status: overview.status,
            is_active: overview.is_active,
            created_at: overview.created_at,
            last_checked_at: overview.last_checked_at,
          })),);
      }
      else {
        return;
      }
      this.overviews.set(Object.fromEntries(snapshot.overviews.map((overview) => [overview.id, overview])),);
      this.error.set('');
      this.loading.set(false);
    });
  }

  target(record: ResourceRecord): string {
    if (record.url) {
      return record.url;
    }
    if (record.host) {
      return record.host;
    }
    if (record.login_url) {
      return record.login_url;
    }
    if (record.expected_heartbeat_interval) {
      return `Every ${record.expected_heartbeat_interval}s`;
    }
    if (record.monitor_type) {
      return `${record.monitor_type} monitor`;
    }
    return 'Configured';
  }

  recordSubtitle(record: ResourceRecord): string {
    const target = this.target(record);
    const method = record.method ? record.method.toUpperCase() : '';
    if (target === record.name) {
      return method || `${record.monitor_type ?? 'Resource'} endpoint`;
    }
    return method ? `${method} · ${target}` : target;
  }

  overview(record: ResourceRecord): MonitorOverview | undefined {
    return this.overviews()[record.id];
  }

  private isMonitorResource(resourceType: keyof RealtimeResources,): resourceType is 'HTTP' | 'API' | 'ping' | 'heartbeat' {
    return ['HTTP', 'API', 'ping', 'heartbeat'].includes(resourceType);
  }

  private resourcesOf(resources: RealtimeResources | undefined, resourceType: keyof RealtimeResources): unknown[] | undefined {
    switch (resourceType) {
      case 'HTTP':
        return resources?.HTTP;
      case 'API':
        return resources?.API;
      case 'ping':
        return resources?.ping;
      case 'heartbeat':
        return resources?.heartbeat;
      case 'auth_profiles':
        return resources?.auth_profiles;
      case 'users':
        return resources?.users;
      case 'status_pages':
        return resources?.status_pages;
      case 'slack_integrations':
        return resources?.slack_integrations;
      case 'email_integrations':
        return resources?.email_integrations;
    }
  }

  deleteResource(record: ResourceRecord): void {
    if (!window.confirm(`Delete “${record.name}”? This action cannot be undone.`)) {
      return;
    }
    this.deletingId.set(record.id);
    const endpoint = this.deletePath().replace(':id', record.id);
    this.api.delete<null>(endpoint).subscribe({
      next: () => {
        this.records.update((records) => records.filter((item) => item.id !== record.id));
        this.showNotice(`${this.resourceLabel()} “${record.name}” deleted.`);
        this.deletingId.set('');
      },
      error: (error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.deletingId.set('');
      },
    });
  }

  toggleActive(record: ResourceRecord): void {
    const stats = this.overview(record);
    if (!stats) {
      return;
    }
    this.updatingId.set(record.id);
    const endpoint = this.updatePath().replace(':id', record.id);
    this.api
      .put<unknown, { is_active: boolean }>(endpoint, { is_active: !stats.is_active })
      .subscribe({
        next: () => {
          const isActive = !stats.is_active;
          this.overviews.update((overviews) => ({
            ...overviews,
            [record.id]: this.realtime.withActiveState(stats, isActive),
          }));
          this.records.update((records) =>
            records.map((item) =>
              item.id === record.id ? { ...item, is_active: isActive } : item,),);
          this.showNotice(`“${record.name}” ${isActive ? 'started' : 'paused'}.`);
          this.updatingId.set('');
        },
        error: (error: unknown) => {
          this.error.set(ApiService.errorMessage(error));
          this.updatingId.set('');
        },
      });
  }

  startRename(record: ResourceRecord): void {
    this.editingId.set(record.id);
    this.editName.set(record.name);
    this.editExpectedJson.set(record.expected_json ? JSON.stringify(record.expected_json, null, 2) : '');
    this.error.set('');
  }

  cancelRename(): void {
    this.editingId.set('');
    this.editName.set('');
    this.editExpectedJson.set('');
  }

  onEditNameInput(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) {
      this.editName.set(target.value);
    }
  }

  onEditExpectedJsonInput(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLTextAreaElement) {
      this.editExpectedJson.set(target.value);
    }
  }

  onRenameSubmit(event: Event, record: ResourceRecord): void {
    event.preventDefault();
    this.saveRename(record);
  }

  saveRename(record: ResourceRecord): void {
    const name = this.editName().trim();
    if (!name) {
      this.error.set('Name is required.');
      return;
    }
    const body: { name: string; expected_json?: Record<string, unknown> | null } = { name };
    if (this.isApiMonitor(record)) {
      try {
        body.expected_json = this.expectedJsonValue();
      }
      catch (error) {
        this.error.set(error instanceof Error ? error.message : 'Expected JSON must be a valid JSON object.');
        return;
      }
    }
    if (name === record.name && (!this.isApiMonitor(record) || JSON.stringify(body.expected_json) === JSON.stringify(record.expected_json ?? null))) {
      this.cancelRename();
      return;
    }
    this.error.set('');
    this.renamingId.set(record.id);
    const endpoint = this.updatePath().replace(':id', record.id);
    this.api.put<unknown, typeof body>(endpoint, body).subscribe({
      next: () => {
        this.records.update((records) => records.map((item) => (item.id === record.id ? { ...item, ...body } : item)));
        this.overviews.update((overviews) => {
          const current = overviews[record.id];
          return current ? { ...overviews, [record.id]: { ...current, name } } : overviews;
        });
        this.showNotice(this.isApiMonitor(record) ? `API monitor “${name}” updated.` : `“${record.name}” renamed to “${name}”.`);
        this.renamingId.set('');
        this.cancelRename();
      },
      error: (error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.renamingId.set('');
      },
    });
  }

  isApiMonitor(record: ResourceRecord): boolean {
    return (record.monitor_type ?? this.resourceType()) === 'API';
  }

  private expectedJsonValue(): Record<string, unknown> | null {
    const value = this.editExpectedJson().trim();
    if (!value) {
      return null;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(value);
    }
    catch {
      throw new Error('Expected JSON must contain valid JSON.');
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('Expected JSON must be a JSON object.');
    }
    return parsed as Record<string, unknown>;
  }

  private showHeartbeatNotice(message: string, heartbeatToken = ''): void {
    this.heartbeatToken.set(heartbeatToken);
    this.showNotice(message, heartbeatToken ? HEARTBEAT_NOTICE_MS : NOTICE_VISIBLE_MS);
  }

  protected override onNoticeHidden(): void {
    this.heartbeatToken.set('');
  }

  private resourceLabel(): string {
    switch (this.resourceType()) {
      case 'HTTP':
        return 'HTTP monitor';
      case 'API':
        return 'API monitor';
      case 'ping':
        return 'Ping monitor';
      case 'heartbeat':
        return 'Heartbeat monitor';
      case 'auth_profiles':
        return 'Auth profile';
      default:
        return 'Resource';
    }
  }

  formatDuration(totalSeconds: number): string {
    return durationText(totalSeconds);
  }

  uptimeSeconds(overview: MonitorOverview): number {
    return this.realtime.liveUptimeSeconds(overview);
  }

  downtimeSeconds(overview: MonitorOverview): number {
    return this.realtime.liveDowntimeSeconds(overview);
  }

  uptimePercentage(overview: MonitorOverview): number | null {
    return this.realtime.liveUptimePercentage(overview);
  }
}
