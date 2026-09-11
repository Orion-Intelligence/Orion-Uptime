import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { IntegrationEditorBase } from '../../shared/base/integration-editor.base';
import { EmailIntegration } from '../../shared/model/models';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';

@Component({
  selector: 'app-email-integration-editor',
  imports: [ReactiveFormsModule, RouterLink, SkeletonComponent],
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
    const messages = new Map<string, string>([
      ['name', 'Integration name is required (up to 100 characters).'],
      ['email', 'Enter a valid recipient email address (up to 320 characters).'],
    ]);
    if (!this.validateForm(this.form, messages)) {
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
