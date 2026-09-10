import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { MonitorOverview, StatusPage } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NoticePageBase } from '../../shared/base/notice-page.base';
import { DeleteConfirmationDialogComponent } from '../../shared/partials/delete-confirmation-dialog/delete-confirmation-dialog.component';

@Component({
  selector: 'app-status-page-list',
  imports: [DatePipe, RouterLink, DeleteConfirmationDialogComponent],
  templateUrl: './status-page-list.component.html',
})
export class StatusPageListComponent extends NoticePageBase {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);

  readonly pages = signal<StatusPage[]>([]);
  readonly overviews = signal<Partial<Record<string, MonitorOverview>>>({});
  readonly loading = signal(true);
  readonly deletingId = signal('');
  readonly deleteTarget = signal<StatusPage | null>(null);
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

  requestDelete(page: StatusPage): void {
    this.deleteTarget.set(page);
  }

  cancelDelete(): void {
    if (this.deletingId()) {
      return;
    }
    this.deleteTarget.set(null);
  }

  confirmDelete(): void {
    const page = this.deleteTarget();
    if (!page || this.deletingId()) {
      return;
    }
    this.deletingId.set(page.id);
    this.api.delete<null>(`/status-pages/${page.id}`).subscribe({
      next: () => {
        this.pages.update((pages) => pages.filter((item) => item.id !== page.id));
        this.deletingId.set('');
        this.deleteTarget.set(null);
        this.showNotice(`Status page “${page.name}” deleted.`);
      },
      error: (error: unknown) => {
        this.deletingId.set('');
        this.error.set(ApiService.errorMessage(error));
      },
    });
  }

  deleteConfirmationMessage(page: StatusPage): string {
    return `Are you sure you want to delete status page “${page.name}”? Its public link will stop working.`;
  }

}
