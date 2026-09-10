import { inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../services/core/api.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NoticePageBase } from './notice-page.base';
import { IntegrationSummary, MonitorOverview, RealtimeResources } from '../model/models';

export abstract class IntegrationListBase<T extends IntegrationSummary> extends NoticePageBase {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);

  readonly integrations = signal<T[]>([]);
  readonly overviews = signal<Partial<Record<string, MonitorOverview>>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly deleteTarget = signal<T | null>(null);
  readonly error = signal('');

  protected abstract readonly channel: string;

  protected abstract readonly label: string;

  protected constructor() {
    super();
    const initialMessage = this.navigationMessage();
    if (initialMessage) {
      this.showNotice(initialMessage);
    }
  }

  monitorNames(integration: T): string[] {
    const overviews = new Map(Object.entries(this.overviews()));
    return integration.monitor_ids
      .map((monitorId) => overviews.get(monitorId)?.name)
      .filter((name): name is string => Boolean(name));
  }

  requestDelete(integration: T): void {
    this.deleteTarget.set(integration);
  }

  cancelDelete(): void {
    if (this.deletingId()) {
      return;
    }
    this.deleteTarget.set(null);
  }

  confirmDelete(): void {
    const integration = this.deleteTarget();
    if (!integration || this.deletingId()) {
      return;
    }
    this.deletingId.set(integration.id);
    this.api.delete<null>(`/integrations/${this.channel}/${integration.id}`).subscribe({
      next: () => {
        this.integrations.update((items) => items.filter((item) => item.id !== integration.id));
        this.deletingId.set('');
        this.deleteTarget.set(null);
        this.showNotice(`${this.label} integration “${integration.name}” deleted.`);
      },
      error: (error: unknown) => {
        this.deletingId.set('');
        this.error.set(ApiService.errorMessage(error));
      },
    });
  }

  abstract deleteConfirmationMessage(integration: T): string;

  protected watch(select: (resources: RealtimeResources) => T[]): void {
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      if (!snapshot.resources) {
        return;
      }
      this.integrations.set(select(snapshot.resources));
      this.overviews.set(Object.fromEntries(snapshot.overviews.map((overview) => [overview.id, overview])));
      this.error.set('');
      this.loading.set(false);
    });
  }

}
