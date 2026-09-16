import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';
import { ApiService } from '../core/api.service';
import { DashboardActivity, DashboardIncident, DashboardSummary, MonitorOverview } from '../../shared/model/models';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiService);

  getSummary(): Observable<DashboardSummary> {
    return this.api.get<DashboardSummary>('/dashboard/summary').pipe(map((response) => response.data));
  }

  getIncidents(): Observable<DashboardIncident[]> {
    return this.api.get<DashboardIncident[]>('/dashboard/incidents').pipe(map((response) => response.data));
  }

  getActivity(): Observable<DashboardActivity[]> {
    return this.api.get<DashboardActivity[]>('/dashboard/activity').pipe(map((response) => response.data));
  }

  getOverviews(): Observable<MonitorOverview[]> {
    return this.api.get<MonitorOverview[]>('/dashboard/monitor-overviews').pipe(map((response) => response.data));
  }
}
