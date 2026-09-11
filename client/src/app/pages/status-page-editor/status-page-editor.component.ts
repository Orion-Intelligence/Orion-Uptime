import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/core/api.service';
import { StatusPage } from '../../shared/model/models';
import { RealtimeService } from '../../services/dashboard/realtime.service';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';
import { MonitorSelectionBase } from '../../shared/base/monitor-selection.base';

@Component({
  selector: 'app-status-page-editor',
  imports: [ReactiveFormsModule, RouterLink, SkeletonComponent],
  templateUrl: './status-page-editor.component.html',
})
export class StatusPageEditorComponent extends MonitorSelectionBase {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly realtime = inject(RealtimeService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly pageId = this.route.snapshot.paramMap.get('id');
  private initialized = false;

  readonly editing = Boolean(this.pageId);
  readonly loading = signal(this.editing);
  readonly submitting = signal(false);
  readonly form = this.formBuilder.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    description: ['', Validators.maxLength(500)],
  });

  constructor() {
    super();
    this.realtime.connect();
    this.realtime.snapshots$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((snapshot) => {
      if (!snapshot.resources) {
        return;
      }
      this.monitors.set(snapshot.overviews);
      if (!this.editing || this.initialized) {
        this.loading.set(false);
        return;
      }
      const page = snapshot.resources.status_pages.find((item) => item.id === this.pageId);
      if (!page) {
        this.error.set('Status page not found.');
        this.loading.set(false);
        return;
      }
      this.form.setValue({ name: page.name, description: page.description });
      this.selectedIds.set(new Set(page.monitor_ids));
      this.initialized = true;
      this.loading.set(false);
    });
  }

  submit(): void {
    const messages = new Map<string, string>([
      ['name', 'Name is required (up to 100 characters).'],
      ['description', 'Description cannot exceed 500 characters.'],
    ]);
    if (!this.validateForm(this.form, messages)) {
      return;
    }
    const values = this.form.getRawValue();
    const body = {
      name: values.name.trim(),
      description: values.description.trim(),
      monitor_ids: [...this.selectedIds()],
    };
    if (!body.name) {
      this.error.set('Status page name is required.');
      return;
    }
    this.submitting.set(true);
    const request = this.editing
      ? this.api.put<StatusPage, typeof body>(`/status-pages/${this.pageId}`, body)
      : this.api.post<StatusPage, typeof body>('/status-pages', body);
    request.subscribe({
      next: (response) => {
        void this.router.navigate(['/status-pages'], {
          state: {
            message: `Status page “${response.data.name}” ${this.editing ? 'updated' : 'created'}.`,
          },
        });
      },
      error: (error: unknown) => {
        this.submitting.set(false);
        this.error.set(ApiService.errorMessage(error));
      },
    });
  }

}
