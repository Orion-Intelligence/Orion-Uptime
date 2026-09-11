import { DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { IntegrationBody, IntegrationSummary } from '../model/models';
import { MonitorSelectionBase } from './monitor-selection.base';

export abstract class IntegrationEditorBase extends MonitorSelectionBase {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly realtime = inject(RealtimeService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly integrationId = this.route.snapshot.paramMap.get('id');
  private monitorsLoaded = false;
  private integrationLoaded = !this.integrationId;

  readonly editing = Boolean(this.integrationId);
  readonly loading = signal(true);
  readonly submitting = signal(false);

  protected abstract readonly channel: string;

  protected abstract readonly label: string;

  protected watch<T extends IntegrationSummary>(apply: (detail: T) => void): void {
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      this.monitors.set(snapshot.overviews);
      this.monitorsLoaded = true;
      this.finishLoading();
    });
    if (!this.integrationId) {
      return;
    }
    this.api.get<T>(`/integrations/${this.channel}/${this.integrationId}`).subscribe({
      next: (response) => {
        apply(response.data);
        this.selectedIds.set(new Set(response.data.monitor_ids));
        this.integrationLoaded = true;
        this.finishLoading();
      },
      error: (error: unknown) => {
        this.error.set(ApiService.errorMessage(error));
        this.integrationLoaded = true;
        this.finishLoading();
      },
    });
  }

  protected persist<T extends IntegrationSummary, B extends IntegrationBody>(body: B): void {
    this.submitting.set(true);
    const request = this.editing
      ? this.api.put<T, B>(`/integrations/${this.channel}/${this.integrationId}`, body)
      : this.api.post<T, B>(`/integrations/${this.channel}`, body);
    request.subscribe({
      next: (response) => {
        void this.router.navigate([`/integrations/${this.channel}`], {
          state: {
            message: `${this.label} integration “${response.data.name}” ${this.editing ? 'updated' : 'created'}.`,
          },
        });
      },
      error: (error: unknown) => {
        this.submitting.set(false);
        this.error.set(ApiService.errorMessage(error));
      },
    });
  }

  private finishLoading(): void {
    if (this.monitorsLoaded && this.integrationLoaded) {
      this.loading.set(false);
    }
  }
}
