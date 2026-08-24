import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { EmailIntegration, MonitorOverview } from '../../shared/model/models';

@Component({
  selector: 'app-email-integration-list',
  imports: [DatePipe, RouterLink],
  templateUrl: './email-integration-list.component.html',
})
export class EmailIntegrationListComponent {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly realtime = inject(RealtimeService);
  private readonly router = inject(Router);
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private noticeRemovalTimer: ReturnType<typeof setTimeout> | undefined;

  readonly integrations = signal<EmailIntegration[]>([]);
  readonly overviews = signal<Partial<Record<string, MonitorOverview>>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly error = signal('');
  readonly message = signal('');
  readonly noticeLeaving = signal(false);

  constructor() {
    const initialMessage = String(this.router.currentNavigation()?.extras.state?.['message'] ?? '');
    if (initialMessage) {
      this.showNotice(initialMessage);
    }
    this.destroyRef.onDestroy(() => {
      this.clearNoticeTimers();
    });
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      if (!snapshot.resources) {
        return;
      }
      this.integrations.set(snapshot.resources.email_integrations);
      this.overviews.set(Object.fromEntries(snapshot.overviews.map((overview) => [overview.id, overview])));
      this.error.set('');
      this.loading.set(false);
    });
  }

  monitorNames(integration: EmailIntegration): string[] {
    const overviews = new Map(Object.entries(this.overviews()));
    return integration.monitor_ids
      .map((monitorId) => overviews.get(monitorId)?.name)
      .filter((name): name is string => Boolean(name));
  }

  deleteIntegration(integration: EmailIntegration): void {
    if (!window.confirm(`Delete “${integration.name}”? Email alerts to ${integration.email} will stop.`)) {
      return;
    }
    this.deletingId.set(integration.id);
    this.api.delete<null>(`/integrations/email/${integration.id}`).subscribe({
      next: () => {
        this.integrations.update((items) => items.filter((item) => item.id !== integration.id));
        this.deletingId.set('');
        this.showNotice(`Email integration “${integration.name}” deleted.`);
      },
      error: (error: unknown) => {
        this.deletingId.set('');
        this.error.set(ApiService.errorMessage(error));
      },
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
      }, 300);
    }, 4000);
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
