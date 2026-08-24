import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { MonitorOverview, SlackIntegrationDetail } from '../../shared/model/models';

@Component({
  selector: 'app-integration-editor',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './integration-editor.component.html',
})
export class IntegrationEditorComponent {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly realtime = inject(RealtimeService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly integrationId = this.route.snapshot.paramMap.get('id');
  private monitorsLoaded = false;
  private integrationLoaded = !this.integrationId;

  readonly editing = Boolean(this.integrationId);
  readonly monitors = signal<MonitorOverview[]>([]);
  readonly selectedIds = signal<Set<string>>(new Set());
  readonly loading = signal(true);
  readonly submitting = signal(false);
  readonly error = signal('');
  readonly form = this.formBuilder.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    webhook_url: ['', [Validators.required, Validators.maxLength(500)]],
  });

  constructor() {
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      this.monitors.set(snapshot.overviews);
      this.monitorsLoaded = true;
      this.finishLoading();
    });
    if (this.integrationId) {
      this.api.get<SlackIntegrationDetail>(`/integrations/slack/${this.integrationId}`).subscribe({
        next: (response) => {
          this.form.setValue({ name: response.data.name, webhook_url: response.data.webhook_url });
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
  }

  isSelected(monitorId: string): boolean {
    return this.selectedIds().has(monitorId);
  }

  toggleMonitor(monitorId: string): void {
    this.selectedIds.update((current) => {
      const selected = new Set(current);
      if (selected.has(monitorId)) {
        selected.delete(monitorId);
      }
      else {
        selected.add(monitorId);
      }
      return selected;
    });
  }

  submit(): void {
    this.error.set('');
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      return;
    }
    const values = this.form.getRawValue();
    const body = {
      name: values.name.trim(),
      webhook_url: values.webhook_url.trim(),
      monitor_ids: [...this.selectedIds()],
    };
    if (!body.name || !body.webhook_url) {
      this.error.set('Integration name and Slack webhook URL are required.');
      return;
    }
    this.submitting.set(true);
    const request = this.editing
      ? this.api.put<SlackIntegrationDetail, typeof body>(`/integrations/slack/${this.integrationId}`, body)
      : this.api.post<SlackIntegrationDetail, typeof body>('/integrations/slack', body);
    request.subscribe({
      next: (response) => {
        void this.router.navigate(['/integrations'], {
          state: {
            message: `Slack integration “${response.data.name}” ${this.editing ? 'updated' : 'created'}.`,
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
