import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { finalize, TimeoutError, timeout } from 'rxjs';
import { ApiService } from '../../services/core/api.service';
import { AuthService } from '../../services/authentication/auth.service';
import { MonitorConfigDocument, MonitorImportResult, MonitorOverview, RealtimeResources, ResourceRecord } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NoticePageBase } from '../../shared/base/notice-page.base';
import { durationText } from '../../shared/utils/duration.util';
import { parseJsonFile } from '../../shared/utils/json-file.util';
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
  readonly renamingId = signal('');
  readonly error = signal('');
  readonly heartbeatToken = signal('');
  readonly importingConfig = signal(false);
  readonly exportingId = signal('');
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

  exportMonitor(record: ResourceRecord): void {
    const resourceType = this.resourceType();
    if (!resourceType || !this.isMonitorResource(resourceType)) {
      return;
    }

    this.error.set('');
    this.exportingId.set(record.id);
    this.api
      .get<MonitorConfigDocument>(`/monitor-configs/${encodeURIComponent(resourceType)}/${encodeURIComponent(record.id)}`)
      .pipe(finalize(() => {
        this.exportingId.set('');
      }))
      .subscribe({
        next: (response) => {
          const contents = JSON.stringify(response.data, null, 2);
          const url = URL.createObjectURL(new Blob([contents], { type: 'application/json' }));
          const link = document.createElement('a');
          link.href = url;
          link.download = `${this.safeFilename(record.name)}.orion-monitor.json`;
          link.click();
          URL.revokeObjectURL(url);
          this.showNotice(`Configuration for “${record.name}” exported.`);
        },
        error: (error: unknown) => {
          this.error.set(ApiService.errorMessage(error));
        },
      });
  }

  async importMonitorConfig(event: Event): Promise<void> {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) {
      return;
    }
    const file = input.files?.item(0);
    input.value = '';
    if (!file) {
      return;
    }

    this.error.set('');
    try {
      const extension = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() : '';
      if (!extension || !['json', 'txt'].includes(extension)) {
        throw new Error(`The file has an unsupported extension${extension ? ` “.${extension}”` : ''}. Monitor configuration files must use .json or .txt.`);
      }
      if (file.size > 1024 * 1024) {
        throw new Error('Monitor configuration files must be 1 MB or smaller.');
      }
      const parsed = parseJsonFile(await file.text());
      if (!parsed.value || typeof parsed.value !== 'object' || Array.isArray(parsed.value)) {
        throw new Error('The selected file must contain one JSON monitor configuration object.');
      }
      const resourceType = this.resourceType();
      if (!resourceType || !this.isMonitorResource(resourceType)) {
        throw new Error('Monitor configurations can only be imported from a monitor tab.');
      }
      const importedMonitorType = (parsed.value as Record<string, unknown>)['monitor_type'];
      if (importedMonitorType !== resourceType) {
        const importedLabel = typeof importedMonitorType === 'string' ? this.monitorTypeLabel(importedMonitorType) : 'The selected file';
        throw new Error(`${importedLabel} cannot be imported from the ${this.monitorTypeLabel(resourceType)} tab. Open the matching monitor tab and import the file there.`);
      }

      this.importingConfig.set(true);
      this.api
        .post<MonitorImportResult, object>(`/monitor-configs/import?expected_monitor_type=${encodeURIComponent(resourceType)}`, parsed.value)
        .pipe(timeout({ first: 30_000 }), finalize(() => {
          this.importingConfig.set(false);
        }))
        .subscribe({
          next: (response) => {
            const result = response.data;
            const action = result.action === 'created' ? 'created' : 'updated';
            const repairMessage = parsed.repaired ? ' Common syntax issues were repaired.' : '';
            this.showHeartbeatNotice(`${this.monitorTypeLabel(result.monitor_type)} “${result.name}” ${action} from configuration.${repairMessage}`, result.heartbeat_token ?? '');
          },
          error: (error: unknown) => {
            this.error.set(error instanceof TimeoutError ? 'The import took too long and was stopped. Check the backend logs and try again.' : ApiService.errorMessage(error));
          },
        });
    }
    catch (error) {
      this.error.set(error instanceof Error ? error.message : 'The monitor configuration file could not be read.');
    }
  }

  startRename(record: ResourceRecord): void {
    this.editingId.set(record.id);
    this.editName.set(record.name);
  }

  cancelRename(): void {
    this.editingId.set('');
    this.editName.set('');
  }

  onEditNameInput(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) {
      this.editName.set(target.value);
    }
  }

  onRenameSubmit(event: Event, record: ResourceRecord): void {
    event.preventDefault();
    this.saveRename(record);
  }

  saveRename(record: ResourceRecord): void {
    const name = this.editName().trim();
    if (!name || name === record.name) {
      this.cancelRename();
      return;
    }
    this.renamingId.set(record.id);
    const endpoint = this.updatePath().replace(':id', record.id);
    this.api.put<unknown, { name: string }>(endpoint, { name }).subscribe({
      next: () => {
        this.records.update((records) => records.map((item) => (item.id === record.id ? { ...item, name } : item)));
        this.overviews.update((overviews) => {
          const current = overviews[record.id];
          return current ? { ...overviews, [record.id]: { ...current, name } } : overviews;
        });
        this.showNotice(`“${record.name}” renamed to “${name}”.`);
        this.renamingId.set('');
        this.cancelRename();
      },
      error: (error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.renamingId.set('');
      },
    });
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

  private monitorTypeLabel(monitorType: string): string {
    switch (monitorType) {
      case 'HTTP':
        return 'HTTP monitor';
      case 'API':
        return 'API monitor';
      case 'ping':
        return 'Ping monitor';
      case 'heartbeat':
        return 'Heartbeat monitor';
      default:
        return 'Monitor';
    }
  }

  private safeFilename(name: string): string {
    const safe = name.trim().replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
    return safe || 'monitor';
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
