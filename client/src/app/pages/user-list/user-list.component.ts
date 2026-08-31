import { DatePipe } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { UserResponse } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { NoticePageBase } from '../../shared/base/notice-page.base';

@Component({
  selector: 'app-user-list-page',
  imports: [DatePipe, RouterLink],
  templateUrl: './user-list.component.html',
})
export class UserListComponent extends NoticePageBase {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);

  readonly users = signal<UserResponse[]>([]);
  readonly loading = signal(true);
  readonly updatingId = signal('');
  readonly deletingId = signal('');
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
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      if (!snapshot.resources) {
        return;
      }
      this.users.set(snapshot.resources.users.filter((user) => user.role === 'viewer'));
      this.error.set('');
      this.loading.set(false);
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

  deleteUser(user: UserResponse): void {
    if (user.role === 'admin') {
      return;
    }
    if (!window.confirm(`Delete “${user.username}”? This action cannot be undone.`)) {
      return;
    }
    this.deletingId.set(user.id);
    this.api.delete<null>(`/users/${user.id}/delete`).subscribe({
      next: () => {
        this.users.update((users) => users.filter((item) => item.id !== user.id));
        this.deletingId.set('');
        this.showNotice(`Viewer “${user.username}” deleted.`);
      },
      error: (error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.deletingId.set('');
      },
    });
  }

}
