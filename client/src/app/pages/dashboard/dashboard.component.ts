import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DashboardActivity, DashboardIncident, DashboardSummary, MonitorOverview, RealtimeSnapshot } from '../../shared/model/models';
import { ApiService } from '../../services/core/api.service';
import { DashboardService } from '../../services/dashboard/dashboard.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { EnterFadeDirective } from '../../shared/animations/enter-fade.directive';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';

@Component({
  selector: 'app-dashboard-page',
  imports: [DatePipe, DecimalPipe, SkeletonComponent, EnterFadeDirective],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  private readonly dashboard = inject(DashboardService);
  private readonly destroyRef = inject(DestroyRef);

  readonly realtime = inject(RealtimeService);
  readonly summary = signal<DashboardSummary | null>(null);
  readonly incidents = signal<DashboardIncident[]>([]);
  readonly activity = signal<DashboardActivity[]>([]);
  readonly overviews = signal<MonitorOverview[]>([]);
  readonly summaryLoading = signal(true);
  readonly incidentsLoading = signal(true);
  readonly activityLoading = signal(true);
  readonly refreshing = signal(false);
  readonly error = signal('');
  readonly loading = computed(() => this.summaryLoading() || this.incidentsLoading() || this.activityLoading());
  readonly healthSegments = computed(() => {
    const data = this.summary();
    if (!data) {
      return [];
    }
    const up = data.monitors_up || 0;
    const down = data.monitors_down || 0;
    const unknown = data.monitors_unknown || 0;
    const total = up + down + unknown;
    if (total === 0) {
      return [];
    }
    const slots = 24;
    const upSlots = Math.round((up / total) * slots);
    const downSlots = Math.min(slots - upSlots, Math.round((down / total) * slots));
    const unknownSlots = slots - upSlots - downSlots;
    return [
      ...Array<string>(upSlots).fill('up'),
      ...Array<string>(downSlots).fill('down'),
      ...Array<string>(unknownSlots).fill('unknown'),
    ];
  });
  readonly overallUptime = computed(() => {
    const overviews = this.overviews();
    if (!overviews.length) {
      return null;
    }
    const percentages = overviews
      .filter((overview) => overview.is_active)
      .map((overview) => this.realtime.liveUptimePercentage(overview))
      .filter((value): value is number => value !== null);
    if (!percentages.length) {
      return null;
    }
    return percentages.reduce((total, value) => total + value, 0) / percentages.length;
  });

  constructor() {
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => this.applySnapshot(snapshot));
    if (!this.realtime.snapshot()) {
      this.loadDashboard();
    }
  }

  private applySnapshot(snapshot: RealtimeSnapshot): void {
    this.summary.set(snapshot.summary);
    this.incidents.set(snapshot.incidents);
    this.activity.set(snapshot.activity);
    this.overviews.set(snapshot.overviews);
    this.summaryLoading.set(false);
    this.incidentsLoading.set(false);
    this.activityLoading.set(false);
    this.refreshing.set(false);
    this.error.set('');
  }

  refresh(): void {
    this.error.set('');
    if (this.realtime.snapshot()) {
      this.refreshing.set(true);
      this.realtime.reconnect();
      return;
    }
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.error.set('');
    if (!this.summary()) {
      this.summaryLoading.set(true);
    }
    if (!this.activity().length) {
      this.activityLoading.set(true);
    }
    if (!this.incidents().length) {
      this.incidentsLoading.set(true);
    }
    this.dashboard.getSummary().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        if (!this.realtime.snapshot()) {
          this.summary.set(data);
        }
        this.summaryLoading.set(false);
      },
      error: (err) => {
        this.error.set(ApiService.errorMessage(err));
        this.summaryLoading.set(false);
      },
    });
    this.dashboard.getActivity().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        if (!this.realtime.snapshot()) {
          this.activity.set(data);
        }
        this.activityLoading.set(false);
      },
      error: (err) => {
        this.error.set(ApiService.errorMessage(err));
        this.activityLoading.set(false);
      },
    });
    this.dashboard.getIncidents().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        if (!this.realtime.snapshot()) {
          this.incidents.set(data);
        }
        this.incidentsLoading.set(false);
      },
      error: (err) => {
        this.error.set(ApiService.errorMessage(err));
        this.incidentsLoading.set(false);
      },
    });
    this.dashboard.getOverviews().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        if (!this.realtime.snapshot()) {
          this.overviews.set(data);
        }
      },
      error: (err) => this.error.set(ApiService.errorMessage(err)),
    });
  }

  formatDuration(seconds: number | null): string {
    if (seconds === null) {
      return 'Ongoing';
    }
    if (seconds < 60) {
      return `${seconds}s`;
    }
    if (seconds < 3600) {
      return `${Math.round(seconds / 60)}m`;
    }
    return `${(seconds / 3600).toFixed(1)}h`;
  }

  incidentDuration(incident: DashboardIncident): string {
    return this.formatDuration(this.realtime.liveIncidentDuration(incident));
  }
}
