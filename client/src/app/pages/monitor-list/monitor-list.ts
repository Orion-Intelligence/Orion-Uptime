import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, DestroyRef, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { MonitorOverview, RealtimeResources, ResourceRecord } from '../../models/models';
import { RealtimeService } from '../../services/realtime.service';

@Component({
  selector: 'app-resource-list-page',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './monitor-list.html',
})
export class ResourceListPage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly resourceType = signal<keyof RealtimeResources | null>(null);
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private noticeRemovalTimer: ReturnType<typeof setTimeout> | undefined;

  readonly title = signal('Resources');
  readonly description = signal('');
  readonly newUrl = signal('');
  readonly detailBase = signal('');
  readonly deletePath = signal('');
  readonly updatePath = signal('');
  readonly records = signal<ResourceRecord[]>([]);
  readonly overviews = signal<Record<string, MonitorOverview>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly updatingId = signal('');
  readonly editingId = signal('');
  readonly editName = signal('');
  readonly renamingId = signal('');
  readonly error = signal('');
  readonly message = signal('');
  readonly heartbeatToken = signal('');
  readonly noticeLeaving = signal(false);
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
    const navigationState = this.router.currentNavigation()?.extras.state;
    const initialMessage = String(navigationState?.['message'] ?? '');
    const initialToken = String(navigationState?.['heartbeatToken'] ?? '');
    if (initialMessage || initialToken) {
      this.showNotice(initialMessage, initialToken);
    }
    this.destroyRef.onDestroy(() => this.clearNoticeTimers());
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
      const resources = snapshot.resources?.[resourceType];
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
  }

  cancelRename(): void {
    this.editingId.set('');
    this.editName.set('');
  }

  onEditNameInput(event: Event): void {
    this.editName.set((event.target as HTMLInputElement).value);
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
        this.overviews.update((overviews) => (overviews[record.id] ? { ...overviews, [record.id]: { ...overviews[record.id], name } } : overviews));
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

  private showNotice(message: string, heartbeatToken = ''): void {
    this.clearNoticeTimers();
    this.noticeLeaving.set(false);
    this.message.set(message);
    this.heartbeatToken.set(heartbeatToken);
    this.noticeTimer = setTimeout(() => {
      this.noticeLeaving.set(true);
      this.noticeRemovalTimer = setTimeout(() => {
        this.message.set('');
        this.heartbeatToken.set('');
        this.noticeLeaving.set(false);
      }, 300);
    },
    heartbeatToken ? 12000 : 4000,);
  }

  private clearNoticeTimers(): void {
    if (this.noticeTimer) {
      clearTimeout(this.noticeTimer);
    }
    if (this.noticeRemovalTimer) {
      clearTimeout(this.noticeRemovalTimer);
    }
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
    if (totalSeconds < 60) {
      return `${totalSeconds}s`;
    }
    if (totalSeconds < 3600) {
      return `${Math.floor(totalSeconds / 60)}m`;
    }
    if (totalSeconds < 86400) {
      return `${Math.floor(totalSeconds / 3600)}h ${Math.floor((totalSeconds % 3600) / 60)}m`;
    }
    return `${Math.floor(totalSeconds / 86400)}d ${Math.floor((totalSeconds % 86400) / 3600)}h`;
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
