import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { IntegrationEditorBase } from '../../shared/base/integration-editor.base';
import { SlackIntegrationDetail } from '../../shared/model/models';

@Component({
  selector: 'app-integration-editor',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './integration-editor.component.html',
})
export class IntegrationEditorComponent extends IntegrationEditorBase {
  private readonly formBuilder = inject(FormBuilder);

  protected readonly channel = 'slack';
  protected readonly label = 'Slack';

  readonly form = this.formBuilder.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    webhook_url: ['', [Validators.required, Validators.maxLength(500)]],
  });

  constructor() {
    super();
    this.watch<SlackIntegrationDetail>((detail) => {
      this.form.setValue({ name: detail.name, webhook_url: detail.webhook_url });
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
    this.persist<SlackIntegrationDetail, typeof body>(body);
  }
}
