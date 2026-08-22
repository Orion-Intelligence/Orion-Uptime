import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { computed, inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ReplaySubject, Subscription } from 'rxjs';
import { DashboardIncident, MonitorOverview, RealtimeSnapshot } from '../models/models';

@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly platformId = inject(PLATFORM_ID);
  private updates = new ReplaySubject<RealtimeSnapshot>(1);
  private source: EventSource | undefined;
  private recovery: Subscription | undefined;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private clockTimer: ReturnType<typeof setInterval> | undefined;
  private retryAttempt = 0;
  private stopped = true;

  readonly snapshot = signal<RealtimeSnapshot | null>(null);
  readonly error = signal('');
  readonly now = signal(Date.now());
  readonly summary = computed(() => this.snapshot()?.summary ?? null);
  readonly incidents = computed(() => this.snapshot()?.incidents ?? []);
  readonly activity = computed(() => this.snapshot()?.activity ?? []);
  readonly overviews = computed(() => this.snapshot()?.overviews ?? []);

  get snapshots$() {
    return this.updates.asObservable();
  }

  connect(): void {
    if (!isPlatformBrowser(this.platformId) || this.source) {
      return;
    }
    this.stopped = false;
    this.startClock();
    this.openStream();
  }

  reconnect(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    this.source?.close();
    this.source = undefined;
    this.retryAttempt = 0;
    this.stopped = false;
    this.openStream();
  }

  disconnect(): void {
    this.stopped = true;
    this.source?.close();
    this.source = undefined;
    this.recovery?.unsubscribe();
    this.recovery = undefined;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
    }
    if (this.clockTimer) {
      clearInterval(this.clockTimer);
    }
    this.retryTimer = undefined;
    this.clockTimer = undefined;
    this.snapshot.set(null);
    this.updates.complete();
    this.updates = new ReplaySubject<RealtimeSnapshot>(1);
  }

  liveUptimeSeconds(overview: MonitorOverview): number {
    if (!overview.is_active || overview.status !== 'up') {
      return overview.current_uptime_seconds;
    }
    return overview.current_uptime_seconds + this.elapsedSince(overview.snapshot_at);
  }

  liveDowntimeSeconds(overview: MonitorOverview): number {
    if (!overview.is_active || overview.status !== 'down') {
      return overview.latest_downtime_seconds;
    }
    return overview.latest_downtime_seconds + this.elapsedSince(overview.snapshot_at);
  }

  liveUptimePercentage(overview: MonitorOverview): number | null {
    if (overview.uptime_percentage === null) {
      return null;
    }
    const elapsed = overview.is_active ? this.elapsedSince(overview.snapshot_at) : 0;
    const measurementSeconds = overview.measurement_seconds + elapsed;
    if (measurementSeconds <= 0) {
      return overview.uptime_percentage;
    }
    const downtimeSeconds =
          overview.downtime_seconds + (overview.is_active && overview.status === 'down' ? elapsed : 0);
    return Math.max(0, Math.min(100, (1 - downtimeSeconds / measurementSeconds) * 100));
  }

  withActiveState(overview: MonitorOverview, isActive: boolean): MonitorOverview {
    const elapsed = overview.is_active ? this.elapsedSince(overview.snapshot_at) : 0;
    return {
      ...overview,
      is_active: isActive,
      current_uptime_seconds: this.liveUptimeSeconds(overview),
      latest_downtime_seconds: this.liveDowntimeSeconds(overview),
      measurement_seconds: overview.measurement_seconds + elapsed,
      downtime_seconds:
        overview.downtime_seconds +
        (overview.is_active && overview.status === 'down' ? elapsed : 0),
      uptime_percentage: this.liveUptimePercentage(overview),
      snapshot_at: new Date(this.now()).toISOString(),
    };
  }

  liveIncidentDuration(incident: DashboardIncident): number {
    if (incident.resolved_at) {
      return incident.duration_seconds ?? 0;
    }
    const now = this.now();
    return Math.max(0, Math.floor((now - Date.parse(incident.started_at)) / 1000));
  }

  private openStream(): void {
    if (this.stopped || this.source) {
      return;
    }
    const source = new EventSource('/api/events', { withCredentials: true });
    this.source = source;
    source.onopen = () => {
      this.error.set('');
      this.retryAttempt = 0;
    };
    source.addEventListener('snapshot', (event) => {
      try {
        const snapshot = JSON.parse((event as MessageEvent<string>).data) as RealtimeSnapshot;
        if (snapshot.revision <= (this.snapshot()?.revision ?? 0)) {
          return;
        }
        this.snapshot.set(snapshot);
        this.updates.next(snapshot);
        this.error.set('');
      }
      catch {
        this.error.set('A live update could not be read. Reconnecting…');
        this.handleStreamFailure();
      }
    });
    source.addEventListener('reauthenticate', () => this.handleStreamFailure());
    source.onerror = () => this.handleStreamFailure();
  }

  private handleStreamFailure(): void {
    this.source?.close();
    this.source = undefined;
    if (this.stopped) {
      return;
    }

    this.recovery?.unsubscribe();
    this.recovery = this.http.get('/api/auth/me', { withCredentials: true }).subscribe({
      next: () => this.scheduleReconnect(),
      error: (error: unknown) => {
        if (error instanceof HttpErrorResponse && error.status === 401) {
          this.disconnect();
          void this.router.navigate(['/login'], { replaceUrl: true });
          return;
        }
        this.error.set('Live updates are reconnecting…');
        this.scheduleReconnect();
      },
    });
  }

  private scheduleReconnect(): void {
    if (this.stopped) {
      return;
    }
    const delay = Math.min(1000 * 2 ** this.retryAttempt, 15000);
    this.retryAttempt += 1;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
    }
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined;
      this.openStream();
    }, delay);
  }

  private startClock(): void {
    if (this.clockTimer) {
      return;
    }
    this.now.set(Date.now());
    this.clockTimer = setInterval(() => this.now.set(Date.now()), 1000);
  }

  private elapsedSince(timestamp: string): number {
    const now = this.now();
    return Math.max(0, Math.floor((now - Date.parse(timestamp)) / 1000));
  }
}
