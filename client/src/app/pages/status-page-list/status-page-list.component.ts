import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { MonitorOverview, StatusPage } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NoticePageBase } from '../../shared/base/notice-page.base';

@Component({
  selector: 'app-status-page-list',
  imports: [DatePipe, RouterLink],
  templateUrl: './status-page-list.component.html',
})
export class StatusPageListComponent extends NoticePageBase {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);

  readonly pages = signal<StatusPage[]>([]);
  readonly overviews = signal<Partial<Record<string, MonitorOverview>>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly error = signal('');

  constructor() {
    super();
    const initialMessage = String(this.router.currentNavigation()?.extras.state?.['message'] ?? '',);
    if (initialMessage) {
      this.showNotice(initialMessage);
    }
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
    const overviews = new Map(Object.entries(this.overviews()));
    return page.monitor_ids
      .map((monitorId) => overviews.get(monitorId)?.name)
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

}
