import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';
import { ApiService } from '../core/api.service';
import { DashboardSnapshot } from '../../shared/model/models';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiService);

  getSnapshot(): Observable<DashboardSnapshot> {
    return this.api.get<DashboardSnapshot>('/dashboard/snapshot').pipe(map((response) => response.data));
  }
}
