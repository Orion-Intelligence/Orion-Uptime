import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DashboardActivity, DashboardIncident, DashboardSummary, MonitorOverview } from '../../shared/model/models';
import { ApiService } from '../../services/core/api.service';
import { DashboardService } from '../../services/dashboard/dashboard.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';

@Component({
  selector: 'app-dashboard-page',
  imports: [DatePipe, DecimalPipe, SkeletonComponent],
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
    const percentages = this.overviews()
      .filter((overview) => overview.is_active)
      .map((overview) => this.realtime.liveUptimePercentage(overview))
      .filter((value): value is number => value !== null);
    if (!percentages.length) {
      return 0;
    }
    return percentages.reduce((total, value) => total + value, 0) / percentages.length;
  });

  constructor() {
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      this.summary.set(snapshot.summary);
      this.incidents.set(snapshot.incidents);
      this.activity.set(snapshot.activity);
      this.overviews.set(snapshot.overviews);
      this.summaryLoading.set(false);
      this.incidentsLoading.set(false);
      this.activityLoading.set(false);
    });
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.error.set('');
    this.summaryLoading.set(true);
    this.incidentsLoading.set(true);
    this.activityLoading.set(true);
    this.dashboard.getSummary().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.summary.set(data);
        this.summaryLoading.set(false);
      },
      error: (err) => {
        this.error.set(ApiService.errorMessage(err));
        this.summaryLoading.set(false);
      },
    });
    this.dashboard.getActivity().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.activity.set(data);
        this.activityLoading.set(false);
      },
      error: () => this.activityLoading.set(false),
    });
    this.dashboard.getIncidents().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.incidents.set(data);
        this.incidentsLoading.set(false);
      },
      error: () => this.incidentsLoading.set(false),
    });
    this.dashboard.getOverviews().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => this.overviews.set(data),
      error: () => undefined,
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
