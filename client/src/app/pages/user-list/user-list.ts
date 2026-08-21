import { DatePipe } from '@angular/common';
import { Component, DestroyRef, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { UserResponse } from '../../models/models';
import { RealtimeService } from '../../services/realtime.service';

@Component({
  selector: 'app-user-list-page',
  imports: [DatePipe, RouterLink],
  templateUrl: './user-list.html',
})
export class UserListPage {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private noticeRemovalTimer: ReturnType<typeof setTimeout> | undefined;

  readonly users = signal<UserResponse[]>([]);
  readonly loading = signal(true);
  readonly updatingId = signal('');
  readonly deletingId = signal('');
  readonly error = signal('');
  readonly message = signal('');
  readonly noticeLeaving = signal(false);

  constructor() {
    const navigationMessage = String(this.router.currentNavigation()?.extras.state?.['message'] ?? '',);
    if (navigationMessage) {
      this.showNotice(navigationMessage);
    }
    this.destroyRef.onDestroy(() => this.clearNoticeTimers());
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
