import { NgTemplateOutlet } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { ApiService } from '../../services/core/api.service';
import { AuthProfileOption, EditableResource } from '../../shared/model/models';

type ResourceKind = 'http' | 'api' | 'ping' | 'heartbeat' | 'orion-script' | 'auth-profile';

const RESOURCE_LABELS: Record<ResourceKind, string> = {
  'http': 'HTTP monitor',
  'api': 'API monitor',
  'ping': 'Ping monitor',
  'heartbeat': 'Heartbeat monitor',
  'orion-script': 'Orion script monitor',
  'auth-profile': 'Auth profile',
};

const RESOURCE_PATHS: Record<ResourceKind, { create: string; read: string; update: string }> = {
  'http': { create: '/HTTP_monitors/create', read: '/HTTP_monitors/:id/get_one', update: '/HTTP_monitors/:id/update' },
  'api': { create: '/API_monitors/create', read: '/API_monitors/:id', update: '/API_monitors/:id' },
  'ping': { create: '/ping-monitors/create', read: '/ping-monitors/:id/get_one', update: '/ping-monitors/:id/update' },
  'heartbeat': { create: '/heartbeat-monitors/create', read: '/heartbeat-monitors/:id/get_one', update: '/heartbeat-monitors/:id/update' },
  'orion-script': { create: '/orion-script-monitors/create', read: '/orion-script-monitors/:id/get_one', update: '/orion-script-monitors/:id/update' },
  'auth-profile': { create: '/auth-profiles/create', read: '/auth-profiles/:id', update: '/auth-profiles/:id' },
};

interface CreatedResource {
  heartbeat_token?: string;
  login_status_code?: number | null;
}

@Component({
  selector: 'app-new-resource-page',
  imports: [ReactiveFormsModule, RouterLink, NgTemplateOutlet],
  templateUrl: './add-monitor.component.html',
})
export class AddMonitorComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly kind = this.route.snapshot.data['kind'] as ResourceKind;
  readonly title = String(this.route.snapshot.data['title']);
  readonly backUrl = String(this.route.snapshot.data['backUrl']);
  readonly editId = this.route.snapshot.paramMap.get('id') ?? '';
  readonly editing = Boolean(this.editId);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly authProfiles = signal<AuthProfileOption[]>([]);
  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    url: [''],
    host: [''],
    method: ['GET'],
    check_interval: [60],
    timeout: [10],
    expected_status_code: [200],
    expected_response_time_ms: [''],
    expected_heartbeat_interval: [60],
    grace_period: [60],
    headers: ['{}'],
    request_body: [''],
    expected_json: [''],
    expected_headers: [''],
    expected_content_type: [''],
    auth_profile_id: [''],
    login_url: [''],
    credentials: ['{\n  "username": "",\n  "password": ""\n}'],
  });

  constructor() {
    if (this.kind === 'api') {
      this.api.get<AuthProfileOption[]>('/auth-profiles/list_all').subscribe({
        next: (response) => {
          this.authProfiles.set(response.data); 
        },
      });
    }
    if (this.editing) {
      this.loading.set(true);
      this.api.get<EditableResource>(this.path('read'))
        .pipe(finalize(() => {
          this.loading.set(false);
        }))
        .subscribe({
          next: (response) => {
            this.populate(response.data);
          },
          error: (error: unknown) => {
            this.error.set(ApiService.errorMessage(error));
          },
        });
    }
  }

  private populate(resource: EditableResource): void {
    const defaults = this.form.getRawValue();
    this.form.patchValue({
      name: resource.name,
      url: resource.url ?? '',
      host: resource.host ?? '',
      method: resource.method ?? defaults.method,
      check_interval: resource.check_interval ?? defaults.check_interval,
      timeout: resource.timeout ?? defaults.timeout,
      expected_status_code: resource.expected_status_code ?? defaults.expected_status_code,
      expected_response_time_ms: resource.expected_response_time_ms == null ? '' : String(resource.expected_response_time_ms),
      expected_heartbeat_interval: resource.expected_heartbeat_interval ?? defaults.expected_heartbeat_interval,
      grace_period: resource.grace_period ?? defaults.grace_period,
      headers: this.jsonText(resource.headers, defaults.headers),
      request_body: this.jsonText(resource.request_body, ''),
      expected_json: this.jsonText(resource.expected_json, ''),
      expected_headers: this.jsonText(resource.expected_headers, ''),
      expected_content_type: resource.expected_content_type ?? '',
      auth_profile_id: resource.auth_profile_id ?? '',
      login_url: resource.login_url ?? '',
      credentials: this.jsonText(resource.credentials, defaults.credentials),
    });
  }

  private jsonText(value: Record<string, unknown> | null | undefined, fallback: string): string {
    return value ? JSON.stringify(value, null, 2) : fallback;
  }

  private path(action: 'create' | 'read' | 'update'): string {
    return RESOURCE_PATHS[this.kind][action].replace(':id', this.editId);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set(this.invalidFieldMessage());
      return;
    }

    this.error.set('');

    let request: { endpoint: string; body: Record<string, unknown> };
    try {
      request = this.buildRequest();
    }
    catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Check the form values.');
      return;
    }

    this.loading.set(true);
    const submission = this.editing
      ? this.api.put<CreatedResource, Record<string, unknown>>(request.endpoint, request.body)
      : this.api.post<CreatedResource, Record<string, unknown>>(request.endpoint, request.body);
    submission
      .pipe(finalize(() => {
        this.loading.set(false); 
      }))
      .subscribe({
        next: (response) => {
          const data = response.data;
          let heartbeatToken = '';
          if (typeof data === 'object' && 'heartbeat_token' in data) {
            heartbeatToken = String(data.heartbeat_token);
          }
          void this.router.navigateByUrl(this.backUrl, {
            state: {
              message: this.creationMessage(String(request.body['name']), data),
              heartbeatToken,
            },
          });
        },
        error: (error: unknown) => {
          this.error.set(ApiService.errorMessage(error)); 
        },
      });
  }

  private creationMessage(name: string, data: CreatedResource): string {
    const loginStatus = this.kind === 'auth-profile' && data.login_status_code ? ` · Login HTTP ${data.login_status_code}` : '';
    return `${RESOURCE_LABELS[this.kind]} “${name}” ${this.editing ? 'updated' : 'created'}${loginStatus}.`;
  }

  private invalidFieldMessage(): string {
    const messages = new Map<string, string>([
      ['name', 'Name is required (up to 100 characters).'],
      ['check_interval', 'Check interval must be between 10 and 86400 seconds.'],
      ['timeout', 'Timeout must be at least 1 second.'],
      ['expected_status_code', 'Expected status must be between 100 and 599.'],
      ['expected_heartbeat_interval', 'Expected heartbeat interval must be at least 1 second.'],
      ['grace_period', 'Grace period cannot be negative.'],
    ]);
    const invalid = Object.keys(this.form.controls).find((key) => this.form.get(key)?.invalid);
    return (invalid === undefined ? undefined : messages.get(invalid)) ?? 'Check the highlighted fields.';
  }

  private buildRequest(): { endpoint: string; body: Record<string, unknown> } {
    const value = this.form.getRawValue();
    const name = this.required(value.name, 'Name');

    switch (this.kind) {
      case 'http':
        return {
          endpoint: this.path(this.editing ? 'update' : 'create'),
          body: {
            name,
            url: this.required(value.url, 'URL'),
            check_interval: value.check_interval,
            timeout: value.timeout,
            expected_status_code: value.expected_status_code,
            expected_response_time_ms: this.optionalNumber(value.expected_response_time_ms),
          },
        };
      case 'ping':
        return {
          endpoint: this.path(this.editing ? 'update' : 'create'),
          body: {
            name,
            host: this.required(value.host, 'Host'),
            check_interval: value.check_interval,
            timeout: value.timeout,
            expected_response_time_ms: this.optionalNumber(value.expected_response_time_ms),
          },
        };
      case 'orion-script':
        return {
          endpoint: this.path(this.editing ? 'update' : 'create'),
          body: {
            name,
            url: this.required(value.url, 'Orion URL'),
            check_interval: value.check_interval,
            timeout: value.timeout,
            expected_response_time_ms: this.optionalNumber(value.expected_response_time_ms),
          },
        };
      case 'heartbeat':
        return {
          endpoint: this.path(this.editing ? 'update' : 'create'),
          body: {
            name,
            expected_heartbeat_interval: value.expected_heartbeat_interval,
            grace_period: value.grace_period,
          },
        };
      case 'auth-profile':
        return {
          endpoint: this.path(this.editing ? 'update' : 'create'),
          body: {
            name,
            login_url: this.required(value.login_url, 'Login URL'),
            credentials: this.jsonObject(value.credentials, 'Credentials', true),
            headers: this.jsonObject(value.headers, 'Headers', true),
          },
        };
      case 'api':
        return {
          endpoint: this.path(this.editing ? 'update' : 'create'),
          body: {
            name,
            url: this.required(value.url, 'URL'),
            method: value.method,
            headers: this.jsonObject(value.headers, 'Headers', true),
            request_body: this.jsonObject(value.request_body, 'Request body'),
            expected_status_code: value.expected_status_code,
            expected_json: this.jsonObject(value.expected_json, 'Expected JSON'),
            check_interval: value.check_interval,
            timeout: value.timeout,
            expected_response_time_ms: this.optionalNumber(value.expected_response_time_ms),
            expected_headers: this.jsonObject(value.expected_headers, 'Expected headers'),
            expected_content_type: value.expected_content_type.trim() || null,
            auth_profile_id: value.auth_profile_id || null,
          },
        };
    }
  }

  private required(value: string, label: string): string {
    const result = value.trim();
    if (!result) {
      throw new Error(`${label} is required.`);
    }
    return result;
  }

  private optionalNumber(value: string): number | null {
    if (!value.trim()) {
      return null;
    }
    const result = Number(value);
    if (!Number.isFinite(result) || result < 0) {
      throw new Error('Expected response time must be a positive number.');
    }
    return result;
  }

  private jsonObject( value: string, label: string, required = false, ): Record<string, unknown> | null {
    if (!value.trim()) {
      if (required) {
        throw new Error(`${label} is required.`);
      }
      return null;
    }
    const parsed = this.parseJson(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(`${label} must be a valid JSON object.`);
    }
    return parsed as Record<string, unknown>;
  }

  private parseJson(value: string): unknown {
    try {
      return JSON.parse(value);
    }
    catch {
      return undefined;
    }
  }
}
