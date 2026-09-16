import { DatePipe } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { UserResponse } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { ResourceService } from '../../services/dashboard/resource.service';
import { NoticePageBase } from '../../shared/base/notice-page.base';
import { DeleteConfirmationDialogComponent } from '../../shared/partials/delete-confirmation-dialog/delete-confirmation-dialog.component';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';
import { EmptyStateComponent } from '../../shared/partials/empty-state/empty-state.component';
import { NotificationComponent } from '../../shared/partials/notification/notification.component';

@Component({
  selector: 'app-user-list-page',
  imports: [DatePipe, RouterLink, DeleteConfirmationDialogComponent, SkeletonComponent, EmptyStateComponent, NotificationComponent],
  templateUrl: './user-list.component.html',
})
export class UserListComponent extends NoticePageBase {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);
  private readonly resources = inject(ResourceService);

  readonly users = signal<UserResponse[]>([]);
  readonly loading = signal(true);
  readonly updatingId = signal('');
  readonly deletingId = signal('');
  readonly deleteTarget = signal<UserResponse | null>(null);
  readonly error = signal('');

  constructor() {
    super();
    const navigationMessage = String(this.router.currentNavigation()?.extras.state?.['message'] ?? '',);
    if (navigationMessage) {
      this.showNotice(navigationMessage);
    }
    this.realtime.connect();
    effect(() => {
      const error = this.realtime.error();
      if (error && this.loading()) {
        this.error.set(error);
      }
    });
    this.realtime.resourceChanges$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((invalidation) => {
      if (invalidation.types.includes('users')) {
        this.loadUsers();
      }
    });
    this.loadUsers();
  }

  loadUsers(): void {
    this.loading.set(true);
    this.error.set('');
    this.resources
      .list<UserResponse>('users')
      .pipe(finalize(() => {
        this.loading.set(false);
      }))
      .subscribe({
        next: (users) => {
          this.users.set(users.filter((user) => user.role === 'viewer'));
        },
        error: (error: unknown) => {
          this.error.set(ApiService.errorMessage(error));
        },
      });
  }

  toggleActive(user: UserResponse): void {
    if (user.role === 'admin') {
      return;
    }
    this.updatingId.set(user.id);
    this.api
      .put<UserResponse, { is_active: boolean }>(`/users/${user.id}/update`, {
        is_active: !user.is_active,
      })
      .subscribe({
        next: (response) => {
          this.users.update((users) =>
            users.map((item) => (item.id === user.id ? response.data : item)),);
          this.updatingId.set('');
          this.showNotice(`${response.data.username} was ${response.data.is_active ? 'activated' : 'deactivated'}.`,);
        },
        error: (error: unknown) => {
          this.error.set(ApiService.errorMessage(error));
          this.updatingId.set('');
        },
      });
  }

  requestDelete(user: UserResponse): void {
    if (user.role === 'admin') {
      return;
    }
    this.deleteTarget.set(user);
  }

  cancelDelete(): void {
    if (this.deletingId()) {
      return;
    }
    this.deleteTarget.set(null);
  }

  confirmDelete(): void {
    const user = this.deleteTarget();
    if (!user || user.role === 'admin' || this.deletingId()) {
      return;
    }
    this.deletingId.set(user.id);
    this.api.delete<null>(`/users/${user.id}/delete`).subscribe({
      next: () => {
        this.users.update((users) => users.filter((item) => item.id !== user.id));
        this.deletingId.set('');
        this.deleteTarget.set(null);
        this.showNotice(`Viewer “${user.username}” deleted.`);
      },
      error: (error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.deletingId.set('');
        this.deleteTarget.set(null);
      },
    });
  }

  deleteConfirmationMessage(user: UserResponse): string {
    return `Are you sure you want to delete viewer “${user.username}”? This action cannot be undone.`;
  }

}
