import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, forkJoin, of } from 'rxjs';
import { ApiService } from '../../services/api.service';
import { MonitorDetail, MonitorIncident, MonitorOverview, RealtimeSnapshot, ResponseHistory, ResponseHistoryPoint, StatusHistory, StatusHistoryPoint, } from '../../models/models';
import { RealtimeService } from '../../services/realtime.service';

interface ChartPoint<T> {
  data: T;
  x: number;
  y: number;
}

@Component({
  selector: 'app-monitor-detail-page',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './monitor-detail.html',
})
export class MonitorDetailPage {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly monitorId = this.route.snapshot.paramMap.get('id') ?? '';

  readonly backUrl = String(this.route.snapshot.data['backUrl']);
  readonly ranges = [ { label: 'Week', days: 7 }, { label: 'Month', days: 30 }, { label: 'Year', days: 365 }, ];
  readonly detail = signal<MonitorDetail | null>(null);
  readonly statusHistory = signal<StatusHistoryPoint[]>([]);
  readonly responseHistory = signal<ResponseHistoryPoint[]>([]);
  readonly statusDays = signal(7);
  readonly responseDays = signal(7);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly statusChartPoints = computed(() =>
    this.chartPoints(this.statusHistory(), (point) => this.statusY(point.status)),);
  readonly responseChartPoints = computed(() => {
    const points = this.responseHistory().filter((point): point is ResponseHistoryPoint & { response_time_ms: number } =>
      point.response_time_ms !== null,);
    const maximum = Math.max(...points.map((point) => point.response_time_ms), 1);
    return this.chartPoints(points, (point) => 125 - (point.response_time_ms / maximum) * 105);
  });

  constructor() {
    this.realtime.connect();
    this.loadInitialData();
    this.realtime.snapshots$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((snapshot) => this.applySnapshot(snapshot));
  }

  private loadInitialData(): void {
    forkJoin({
      detail: this.api.get<MonitorDetail>(`/dashboard/monitors/${this.monitorId}`),
      status: this.api.get<StatusHistory>(`/dashboard/status-history/${this.monitorId}?days=${this.statusDays()}`,),
      response: this.api.get<ResponseHistory>(`/dashboard/response-history/${this.monitorId}?days=${this.responseDays()}`,),
    })
      .pipe(catchError((error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.loading.set(false);
        return of(null);
      }),
      takeUntilDestroyed(this.destroyRef),)
      .subscribe((result) => {
        if (result === null) {
          return;
        }
        this.detail.set(result.detail.data);
        this.statusHistory.set(this.mergeStatusPoints(this.statusHistory(), result.status.data.history),);
        this.responseHistory.set(this.mergeResponsePoints(this.responseHistory(), result.response.data.points),);
        this.error.set('');
        this.loading.set(false);
      });
  }

  setStatusRange(days: number): void {
    this.statusDays.set(days);
    this.api
      .get<StatusHistory>(`/dashboard/status-history/${this.monitorId}?days=${days}`)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          if (this.statusDays() === days) {
            this.statusHistory.set(this.mergeStatusPoints([], response.data.history));
          }
        },
        error: (error: unknown) => this.error.set(ApiService.errorMessage(error)),
      });
  }

  setResponseRange(days: number): void {
    this.responseDays.set(days);
    this.api
      .get<ResponseHistory>(`/dashboard/response-history/${this.monitorId}?days=${days}`)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          if (this.responseDays() === days) {
            this.responseHistory.set(this.mergeResponsePoints([], response.data.points));
          }
        },
        error: (error: unknown) => this.error.set(ApiService.errorMessage(error)),
      });
  }

  statusPolyline(): string {
    return this.statusChartPoints()
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');
  }

  responsePolyline(): string {
    return this.responseChartPoints()
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');
  }

  maximumResponseTime(): number {
    return Math.max(...this.responseHistory().map((point) => point.response_time_ms ?? 0), 0);
  }

  firstDate(points: Array<StatusHistoryPoint | ResponseHistoryPoint>): string | null {
    return points[0]?.checked_at ?? null;
  }

  lastDate(points: Array<StatusHistoryPoint | ResponseHistoryPoint>): string | null {
    return points.at(-1)?.checked_at ?? null;
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

  uptimeSeconds(overview: MonitorOverview): number {
    return this.realtime.liveUptimeSeconds(overview);
  }

  downtimeSeconds(overview: MonitorOverview): number {
    return this.realtime.liveDowntimeSeconds(overview);
  }

  uptimePercentage(overview: MonitorOverview): number | null {
    return this.realtime.liveUptimePercentage(overview);
  }

  incidentDuration(incident: MonitorIncident): number {
    if (incident.resolved_at) {
      return incident.duration_seconds;
    }
    const now = this.realtime.now();
    return Math.max(0, Math.floor((now - Date.parse(incident.started_at)) / 1000));
  }

  private applySnapshot(snapshot: RealtimeSnapshot): void {
    const changedDetail = snapshot.changed_monitor_details[this.monitorId];
    if (changedDetail) {
      this.detail.set(changedDetail);
    }
    else {
      const overview = snapshot.overviews.find((item) => item.id === this.monitorId);
      const current = this.detail();
      if (overview && current) {
        this.detail.set({ ...current, ...overview });
      }
    }

    const activity = snapshot.activity.filter((item) => item.monitor_id === this.monitorId);
    this.statusHistory.update((current) =>
      this.mergeStatusPoints(current,
        activity.map((item) => ({ checked_at: item.checked_at, status: item.status })),),);
    this.responseHistory.update((current) =>
      this.mergeResponsePoints(current,
        activity.map((item) => ({
          checked_at: item.checked_at,
          response_time_ms: item.response_time_ms,
        })),),);
  }

  private mergeStatusPoints( current: StatusHistoryPoint[], incoming: StatusHistoryPoint[], ): StatusHistoryPoint[] {
    const cutoff = Date.now() - this.statusDays() * 24 * 60 * 60 * 1000;
    return [
      ...new Map([...current, ...incoming].map((point) => [point.checked_at, point])).values(),
    ]
      .filter((point) => Date.parse(point.checked_at) >= cutoff)
      .sort((left, right) => Date.parse(left.checked_at) - Date.parse(right.checked_at));
  }

  private mergeResponsePoints( current: ResponseHistoryPoint[], incoming: ResponseHistoryPoint[], ): ResponseHistoryPoint[] {
    const cutoff = Date.now() - this.responseDays() * 24 * 60 * 60 * 1000;
    return [
      ...new Map([...current, ...incoming].map((point) => [point.checked_at, point])).values(),
    ]
      .filter((point) => Date.parse(point.checked_at) >= cutoff)
      .sort((left, right) => Date.parse(left.checked_at) - Date.parse(right.checked_at));
  }

  private statusY(status: StatusHistoryPoint['status']): number {
    if (status === 'up') {
      return 20;
    }
    if (status === 'down') {
      return 120;
    }
    return 70;
  }

  private chartPoints<T>(points: T[], yValue: (point: T) => number): ChartPoint<T>[] {
    const width = 760;
    return points.map((point, index) => {
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
      return { data: point, x, y: yValue(point) };
    });
  }
}
