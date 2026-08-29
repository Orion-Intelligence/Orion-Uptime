import { DestroyRef, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { NOTICE_FADE_MS, NOTICE_VISIBLE_MS } from '../constants/ui.constants';

export abstract class NoticePageBase {
  private noticeTimer: ReturnType<typeof setTimeout> | undefined;
  private noticeRemovalTimer: ReturnType<typeof setTimeout> | undefined;

  protected readonly destroyRef = inject(DestroyRef);
  protected readonly router = inject(Router);

  readonly message = signal('');
  readonly noticeLeaving = signal(false);

  protected constructor() {
    this.destroyRef.onDestroy(() => {
      this.clearNoticeTimers();
    });
  }

  protected navigationState(): Record<string, unknown> | undefined {
    return this.router.currentNavigation()?.extras.state;
  }

  protected navigationMessage(): string {
    return String(this.navigationState()?.['message'] ?? '');
  }

  protected showNotice(message: string, visibleMs: number = NOTICE_VISIBLE_MS): void {
    this.clearNoticeTimers();
    this.noticeLeaving.set(false);
    this.message.set(message);
    this.noticeTimer = setTimeout(() => {
      this.noticeLeaving.set(true);
      this.noticeRemovalTimer = setTimeout(() => {
        this.message.set('');
        this.noticeLeaving.set(false);
        this.onNoticeHidden();
      }, NOTICE_FADE_MS);
    }, visibleMs);
  }

  protected onNoticeHidden(): void {
    return;
  }

  protected clearNoticeTimers(): void {
    if (this.noticeTimer) {
      clearTimeout(this.noticeTimer);
    }
    if (this.noticeRemovalTimer) {
      clearTimeout(this.noticeRemovalTimer);
    }
  }
}
