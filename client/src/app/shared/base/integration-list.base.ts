import { DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NOTICE_FADE_MS, NOTICE_VISIBLE_MS } from '../constants/ui.constants';
import { IntegrationSummary, MonitorOverview, RealtimeResources } from '../model/models';

export abstract class IntegrationListBase<T extends IntegrationSummary> {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly realtime = inject(RealtimeService);
  private readonly router = inject(Router);
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private noticeRemovalTimer: ReturnType<typeof setTimeout> | undefined;

  readonly integrations = signal<T[]>([]);
  readonly overviews = signal<Partial<Record<string, MonitorOverview>>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly error = signal('');
  readonly message = signal('');
  readonly noticeLeaving = signal(false);

  protected abstract readonly channel: string;

  protected abstract readonly label: string;

  protected constructor() {
    const initialMessage = String(this.router.currentNavigation()?.extras.state?.['message'] ?? '');
    if (initialMessage) {
      this.showNotice(initialMessage);
    }
    this.destroyRef.onDestroy(() => {
      this.clearNoticeTimers();
    });
  }

  monitorNames(integration: T): string[] {
    const overviews = new Map(Object.entries(this.overviews()));
    return integration.monitor_ids
      .map((monitorId) => overviews.get(monitorId)?.name)
      .filter((name): name is string => Boolean(name));
  }

  deleteIntegration(integration: T): void {
    if (!window.confirm(this.confirmMessage(integration))) {
      return;
    }
    this.deletingId.set(integration.id);
    this.api.delete<null>(`/integrations/${this.channel}/${integration.id}`).subscribe({
      next: () => {
        this.integrations.update((items) => items.filter((item) => item.id !== integration.id));
        this.deletingId.set('');
        this.showNotice(`${this.label} integration “${integration.name}” deleted.`);
      },
      error: (error: unknown) => {
        this.deletingId.set('');
        this.error.set(ApiService.errorMessage(error));
      },
    });
  }

  protected abstract confirmMessage(integration: T): string;

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

  private showNotice(message: string): void {
    this.clearNoticeTimers();
    this.noticeLeaving.set(false);
    this.message.set(message);
    this.noticeTimer = setTimeout(() => {
      this.noticeLeaving.set(true);
      this.noticeRemovalTimer = setTimeout(() => {
        this.message.set('');
        this.noticeLeaving.set(false);
      }, NOTICE_FADE_MS);
    }, NOTICE_VISIBLE_MS);
  }

  private clearNoticeTimers(): void {
    if (this.noticeTimer) {
      clearTimeout(this.noticeTimer);
    }
    if (this.noticeRemovalTimer) {
      clearTimeout(this.noticeRemovalTimer);
    }
  }
}
