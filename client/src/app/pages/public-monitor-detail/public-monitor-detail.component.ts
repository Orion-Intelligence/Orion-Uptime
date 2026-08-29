import { DatePipe, DecimalPipe, NgOptimizedImage, isPlatformBrowser } from '@angular/common';
import { Component, computed, inject, PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { PublicStreamPageBase } from '../../shared/base/public-stream.base';
import { durationText } from '../../shared/utils/duration.util';
import { ChartPoint, PublicMonitorDetail, PublicMonitorEvent, PublicResponseTimePoint, PublicUptimeStatus, } from '../../shared/model/models';

@Component({
  selector: 'app-public-monitor-detail',
  imports: [DatePipe, DecimalPipe, NgOptimizedImage, RouterLink],
  templateUrl: './public-monitor-detail.component.html',
})
export class PublicMonitorDetailComponent extends PublicStreamPageBase {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly route = inject(ActivatedRoute);
  private readonly monitorId = this.route.snapshot.paramMap.get('monitorId') ?? '';

  readonly slug = this.route.snapshot.paramMap.get('slug') ?? '';
  readonly detail = signal<PublicMonitorDetail | null>(null);
  readonly chartPoints = computed<ChartPoint<PublicResponseTimePoint>[]>(() => {
    const points = this.detail()?.response_time_points ?? [];
    const maximum = Math.max(...points.map((point) => point.response_time_ms), 1);
    return points.map((point, index) => ({
      data: point,
      x: points.length === 1 ? 450 : (index / (points.length - 1)) * 900,
      y: 155 - (point.response_time_ms / maximum) * 125,
    }));
  });

  constructor() {
    super();
    if (isPlatformBrowser(this.platformId)) {
      this.connect();
    }
  }

  responsePolyline(): string {
    return this.chartPoints()
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');
  }

  eventTitle(event: PublicMonitorEvent, monitorName: string): string {
    if (event.event_type === 'created') {
      return `${monitorName} was created`;
    }
    if (event.event_type === 'down') {
      return `${monitorName} went down`;
    }
    return `${monitorName} went up again`;
  }

  eventDuration(event: PublicMonitorEvent): number | null {
    if (event.duration_seconds === null) {
      return null;
    }
    if (!event.ongoing) {
      return event.duration_seconds;
    }
    return Math.max(0, Math.floor((this.now() - Date.parse(event.occurred_at)) / 1000));
  }

  formatDuration(totalSeconds: number): string {
    return durationText(totalSeconds, true);
  }

  uptimeWindows(uptime: PublicUptimeStatus): Array<{ label: string; value: number | null }> {
    return [
      { label: 'Last 24 hours', value: uptime.last_24_hours },
      { label: 'Last 7 days', value: uptime.last_7_days },
      { label: 'Last 30 days', value: uptime.last_30_days },
      { label: 'Last 90 days', value: uptime.last_90_days },
    ];
  }

  protected connect(): void {
    this.clockTimer ??= setInterval(() => {
      this.now.set(Date.now());
    }, 1000);
    this.source = new EventSource(`/api/status-pages/public/${encodeURIComponent(this.slug)}/monitors/${encodeURIComponent(this.monitorId)}/events`,);
    this.source.onopen = () => {
      this.connected.set(true);
      this.error.set('');
      this.resetReconnectDelay();
    };
    this.source.addEventListener('snapshot', (event) => {
      try {
        const incoming = JSON.parse((event as MessageEvent<string>).data) as PublicMonitorDetail;
        const current = this.detail();
        const currentEventIds = current?.recent_events.map((item) => item.event_id).join('|');
        const incomingEventIds = incoming.recent_events.map((item) => item.event_id).join('|');
        this.detail.set(current && currentEventIds === incomingEventIds
          ? { ...incoming, recent_events: current.recent_events }
          : incoming,);
        this.loading.set(false);
        this.connected.set(true);
        this.error.set('');
      }
      catch {
        this.error.set('The latest monitor update could not be displayed.');
      }
    });
    this.source.addEventListener('deleted', () => {
      this.source?.close();
      this.clearReconnect();
      this.connected.set(false);
      this.loading.set(false);
      this.detail.set(null);
      this.error.set('This monitor is no longer published on this status page.');
    });
    this.source.onerror = () => {
      this.connected.set(false);
      if (!this.detail()) {
        this.loading.set(false);
        this.error.set('This public monitor is unavailable.');
      }
      if (this.source?.readyState === EventSource.CLOSED) {
        this.scheduleReconnect();
      }
    };
  }
}
