import { DatePipe, DecimalPipe, NgOptimizedImage, isPlatformBrowser } from '@angular/common';
import { Component, computed, DestroyRef, inject, PLATFORM_ID, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DailyUptime, PublicMonitorDetail, PublicMonitorEvent, PublicResponseTimePoint, PublicStatusMonitor, PublicUptimeStatus, } from '../../shared/model/models';

interface ChartPoint {
  data: PublicResponseTimePoint;
  x: number;
  y: number;
}

@Component({
  selector: 'app-public-monitor-detail',
  imports: [DatePipe, DecimalPipe, NgOptimizedImage, RouterLink],
  templateUrl: './public-monitor-detail.component.html',
})
export class PublicMonitorDetailComponent {
  private readonly destroyRef = inject(DestroyRef);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly route = inject(ActivatedRoute);
  private readonly monitorId = this.route.snapshot.paramMap.get('monitorId') ?? '';
  private source: EventSource | undefined;
  private clockTimer: ReturnType<typeof setInterval> | undefined;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private reconnectDelayMs = 2000;

  readonly slug = this.route.snapshot.paramMap.get('slug') ?? '';
  readonly detail = signal<PublicMonitorDetail | null>(null);
  readonly loading = signal(true);
  readonly connected = signal(false);
  readonly error = signal('');
  readonly now = signal(Date.now());
  readonly chartPoints = computed<ChartPoint[]>(() => {
    const points = this.detail()?.response_time_points ?? [];
    const maximum = Math.max(...points.map((point) => point.response_time_ms), 1);
    return points.map((point, index) => ({
      data: point,
      x: points.length === 1 ? 450 : (index / (points.length - 1)) * 900,
      y: 155 - (point.response_time_ms / maximum) * 125,
    }));
  });

  constructor() {
    if (isPlatformBrowser(this.platformId)) {
      this.connect();
    }
    this.destroyRef.onDestroy(() => {
      this.source?.close();
      this.clearReconnect();
      if (this.clockTimer) {
        clearInterval(this.clockTimer);
      }
    });
  }

  monitorStatus(monitor: PublicStatusMonitor): string {
    return monitor.is_active ? monitor.status : 'paused';
  }

  dayClass(day: DailyUptime): string {
    if (day.uptime_percentage === null) {
      return 'no-data';
    }
    if (day.uptime_percentage >= 100) {
      return 'up';
    }
    if (day.uptime_percentage >= 90) {
      return 'good';
    }
    if (day.uptime_percentage >= 75) {
      return 'minor';
    }
    if (day.uptime_percentage >= 50) {
      return 'major';
    }
    if (day.uptime_percentage >= 25) {
      return 'severe';
    }
    return 'down';
  }

  dayLabel(day: DailyUptime): string {
    const percentage =
      day.uptime_percentage === null ? 'No data' : `${day.uptime_percentage.toFixed(2)}% uptime`;
    return `${day.date} · ${percentage}`;
  }

  uptimeWindows(uptime: PublicUptimeStatus): Array<{ label: string; value: number | null }> {
    return [
      { label: 'Last 24 hours', value: uptime.last_24_hours },
      { label: 'Last 7 days', value: uptime.last_7_days },
      { label: 'Last 30 days', value: uptime.last_30_days },
      { label: 'Last 90 days', value: uptime.last_90_days },
    ];
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
    if (totalSeconds < 60) {
      return `${totalSeconds}s`;
    }
    if (totalSeconds < 3600) {
      return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`;
    }
    if (totalSeconds < 86400) {
      return `${Math.floor(totalSeconds / 3600)}h ${Math.floor((totalSeconds % 3600) / 60)}m`;
    }
    return `${Math.floor(totalSeconds / 86400)}d ${Math.floor((totalSeconds % 86400) / 3600)}h`;
  }

  private connect(): void {
    this.clockTimer ??= setInterval(() => {
      this.now.set(Date.now());
    }, 1000);
    this.source = new EventSource(`/api/status-pages/public/${encodeURIComponent(this.slug)}/monitors/${encodeURIComponent(this.monitorId)}/events`,);
    this.source.onopen = () => {
      this.connected.set(true);
      this.error.set('');
      this.reconnectDelayMs = 2000;
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

  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      return;
    }
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      this.source?.close();
      this.connect();
    }, this.reconnectDelayMs);
    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, 30000);
  }

  private clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
  }
}
