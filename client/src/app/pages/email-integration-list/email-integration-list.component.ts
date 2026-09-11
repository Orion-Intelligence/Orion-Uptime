import { DatePipe } from '@angular/common';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { IntegrationListBase } from '../../shared/base/integration-list.base';
import { EmailIntegration, RealtimeResources } from '../../shared/model/models';
import { DeleteConfirmationDialogComponent } from '../../shared/partials/delete-confirmation-dialog/delete-confirmation-dialog.component';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';
import { EmptyStateComponent } from '../../shared/partials/empty-state/empty-state.component';

@Component({
  selector: 'app-email-integration-list',
  imports: [DatePipe, RouterLink, DeleteConfirmationDialogComponent, SkeletonComponent, EmptyStateComponent],
  templateUrl: './email-integration-list.component.html',
})
export class EmailIntegrationListComponent extends IntegrationListBase<EmailIntegration> {
  protected readonly channel = 'email';
  protected readonly label = 'Email';

  constructor() {
    super();
    this.watch((resources: RealtimeResources) => resources.email_integrations);
  }

  deleteConfirmationMessage(integration: EmailIntegration): string {
    return `Are you sure you want to delete Email integration “${integration.name}”? Email alerts to ${integration.email} will stop.`;
  }
}
