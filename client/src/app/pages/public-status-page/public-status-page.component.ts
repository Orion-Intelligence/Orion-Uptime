import { DatePipe, DecimalPipe, NgOptimizedImage, isPlatformBrowser } from '@angular/common';
import { Component, inject, PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { PublicStreamPageBase } from '../../shared/base/public-stream.base';
import { PublicStatusPage, PublicUptimeStatus } from '../../shared/model/models';

@Component({
  selector: 'app-public-status-page',
  imports: [DatePipe, DecimalPipe, NgOptimizedImage, RouterLink],
  templateUrl: './public-status-page.component.html',
})
export class PublicStatusPageComponent extends PublicStreamPageBase {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly slug = inject(ActivatedRoute).snapshot.paramMap.get('slug') ?? '';

  readonly page = signal<PublicStatusPage | null>(null);

  constructor() {
    super();
    if (isPlatformBrowser(this.platformId)) {
      this.clockTimer = setInterval(() => {
        this.now.set(Date.now()); 
      }, 1000);
      this.connect();
    }
  }

  nextUpdateIn(page: PublicStatusPage): number {
    const interval = Math.max(1, page.refresh_interval_seconds);
    const elapsed = Math.max(0, Math.floor((this.now() - Date.parse(page.generated_at)) / 1000));
    return Math.max(0, interval - elapsed);
  }

  uptimeWindows(page: PublicStatusPage): Array<{
    label: string;
    value: number | null;
  }> {
    const uptime: PublicUptimeStatus = page.uptime_status;
    return [
      { label: 'Last 24 hours', value: uptime.last_24_hours },
      { label: 'Last 7 days', value: uptime.last_7_days },
      { label: 'Last 30 days', value: uptime.last_30_days },
      { label: 'Last 90 days', value: uptime.last_90_days },
    ];
  }

  protected connect(): void {
    const source = new EventSource(`/api/status-pages/public/${encodeURIComponent(this.slug)}/events`,);
    this.source = source;
    source.onopen = () => {
      this.error.set('');
      this.resetReconnectDelay();
    };
    source.addEventListener('snapshot', (event) => {
      try {
        this.page.set(JSON.parse((event as MessageEvent<string>).data) as PublicStatusPage);
        this.loading.set(false);
        this.error.set('');
      }
      catch {
        this.error.set('The latest status update could not be displayed.');
      }
    });
    source.addEventListener('deleted', () => {
      this.source?.close();
      this.clearReconnect();
      this.loading.set(false);
      this.page.set(null);
      this.error.set('This status page is no longer available.');
    });
    source.onerror = () => {
      if (!this.page()) {
        this.loading.set(false);
        this.error.set('This status page is unavailable.');
      }
      if (source.readyState === EventSource.CLOSED) {
        this.scheduleReconnect();
      }
    };
  }
}
