import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { DashboardIncident } from '../../models/models';
import { RealtimeService } from '../../services/realtime.service';

@Component({
  selector: 'app-dashboard-page',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './dashboard.html',
})
export class DashboardPage {
  readonly realtime = inject(RealtimeService);
  readonly summary = this.realtime.summary;
  readonly incidents = this.realtime.incidents;
  readonly activity = this.realtime.activity;
  readonly loading = computed(() => this.realtime.snapshot() === null);
  readonly error = this.realtime.error;
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
    const percentages = this.realtime
      .overviews()
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
  }

  loadDashboard(): void {
    this.realtime.reconnect();
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
