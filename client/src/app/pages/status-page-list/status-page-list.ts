import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { MonitorOverview, StatusPage } from '../../models/models';
import { RealtimeService } from '../../services/realtime.service';
import { fadeInOutAnimation, listStaggerAnimation, pageEnterAnimation } from '../../shared/animations';

@Component({
  selector: 'app-status-page-list',
  imports: [DatePipe, RouterLink],
  templateUrl: './status-page-list.html',
  animations: [fadeInOutAnimation, listStaggerAnimation, pageEnterAnimation],
})
export class StatusPageListPage {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly realtime = inject(RealtimeService);
  private readonly router = inject(Router);
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private noticeRemovalTimer: ReturnType<typeof setTimeout> | undefined;

  readonly pages = signal<StatusPage[]>([]);
  readonly overviews = signal<Record<string, MonitorOverview>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly error = signal('');
  readonly message = signal('');
  readonly noticeLeaving = signal(false);

  constructor() {
    const initialMessage = String(this.router.currentNavigation()?.extras.state?.['message'] ?? '',);
    if (initialMessage) {
      this.showNotice(initialMessage);
    }
    this.destroyRef.onDestroy(() => this.clearNoticeTimers());
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      if (!snapshot.resources) {
        return;
      }
      this.pages.set(snapshot.resources.status_pages);
      this.overviews.set(Object.fromEntries(snapshot.overviews.map((overview) => [overview.id, overview])),);
      this.error.set('');
      this.loading.set(false);
    });
  }

  monitorNames(page: StatusPage): string[] {
    const overviews = this.overviews();
    return page.monitor_ids
      .map((monitorId) => overviews[monitorId]?.name)
      .filter((name): name is string => Boolean(name));
  }

  deletePage(page: StatusPage): void {
    if (!window.confirm(`Delete “${page.name}”? Its public link will stop working.`)) {
      return;
    }
    this.deletingId.set(page.id);
    this.api.delete<null>(`/status-pages/${page.id}`).subscribe({
      next: () => {
        this.pages.update((pages) => pages.filter((item) => item.id !== page.id));
        this.deletingId.set('');
        this.showNotice(`Status page “${page.name}” deleted.`);
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
