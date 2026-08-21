import { NgTemplateOutlet } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { ApiService } from '../../services/api.service';
import { AuthProfileOption } from '../../models/models';

type ResourceKind = 'http' | 'api' | 'ping' | 'heartbeat' | 'auth-profile';

interface CreatedResource {
  heartbeat_token?: string;
  login_status_code?: number | null;
}

@Component({
  selector: 'app-new-resource-page',
  imports: [ReactiveFormsModule, RouterLink, NgTemplateOutlet],
  templateUrl: './add-monitor.html',
})
export class NewResourcePage {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly kind = this.route.snapshot.data['kind'] as ResourceKind;
  readonly title = String(this.route.snapshot.data['title']);
  readonly backUrl = String(this.route.snapshot.data['backUrl']);
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
        next: (response) => this.authProfiles.set(response.data),
      });
    }
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
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
    this.api
      .post<CreatedResource, Record<string, unknown>>(request.endpoint, request.body)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (response) => {
          const data = response.data;
          let heartbeatToken = '';
          if (data && typeof data === 'object' && 'heartbeat_token' in data) {
            heartbeatToken = String(data.heartbeat_token);
          }
          void this.router.navigateByUrl(this.backUrl, {
            state: {
              message: this.creationMessage(String(request.body['name']), data),
              heartbeatToken,
            },
          });
        },
        error: (error: unknown) => this.error.set(ApiService.errorMessage(error)),
      });
  }

  private creationMessage(name: string, data: CreatedResource): string {
    switch (this.kind) {
      case 'http':
        return `HTTP monitor “${name}” created.`;
      case 'api':
        return `API monitor “${name}” created.`;
      case 'ping':
        return `Ping monitor “${name}” created.`;
      case 'heartbeat':
        return `Heartbeat monitor “${name}” created.`;
      case 'auth-profile':
        return data.login_status_code
          ? `Auth profile “${name}” created · Login HTTP ${data.login_status_code}.`
          : `Auth profile “${name}” created.`;
    }
  }

  private buildRequest(): { endpoint: string; body: Record<string, unknown> } {
    const value = this.form.getRawValue();
    const name = this.required(value.name, 'Name');

    switch (this.kind) {
      case 'http':
        return {
          endpoint: '/HTTP_monitors/create',
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
          endpoint: '/ping-monitors/create',
          body: {
            name,
            host: this.required(value.host, 'Host'),
            check_interval: value.check_interval,
            timeout: value.timeout,
            expected_response_time_ms: this.optionalNumber(value.expected_response_time_ms),
          },
        };
      case 'heartbeat':
        return {
          endpoint: '/heartbeat-monitors/create',
          body: {
            name,
            expected_heartbeat_interval: value.expected_heartbeat_interval,
            grace_period: value.grace_period,
          },
        };
      case 'auth-profile':
        return {
          endpoint: '/auth-profiles/create',
          body: {
            name,
            login_url: this.required(value.login_url, 'Login URL'),
            credentials: this.jsonObject(value.credentials, 'Credentials', true),
            headers: this.jsonObject(value.headers, 'Headers', true),
          },
        };
      case 'api':
        return {
          endpoint: '/API_monitors/create',
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
