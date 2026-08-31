import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { IntegrationEditorBase } from '../../shared/base/integration-editor.base';
import { EmailIntegration } from '../../shared/model/models';

@Component({
  selector: 'app-email-integration-editor',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './email-integration-editor.component.html',
})
export class EmailIntegrationEditorComponent extends IntegrationEditorBase {
  private readonly formBuilder = inject(FormBuilder);

  protected readonly channel = 'email';
  protected readonly label = 'Email';

  readonly form = this.formBuilder.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    email: ['', [Validators.required, Validators.email, Validators.maxLength(320)]],
  });

  constructor() {
    super();
    this.watch<EmailIntegration>((detail) => {
      this.form.setValue({ name: detail.name, email: detail.email });
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
      email: values.email.trim(),
      monitor_ids: [...this.selectedIds()],
    };
    if (!body.name || !body.email) {
      this.error.set('Integration name and recipient email are required.');
      return;
    }
    this.persist<EmailIntegration, typeof body>(body);
  }
}
