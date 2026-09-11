import { DatePipe } from '@angular/common';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { IntegrationListBase } from '../../shared/base/integration-list.base';
import { RealtimeResources, SlackIntegration } from '../../shared/model/models';
import { DeleteConfirmationDialogComponent } from '../../shared/partials/delete-confirmation-dialog/delete-confirmation-dialog.component';
import { SkeletonComponent } from '../../shared/partials/skeleton/skeleton.component';

@Component({
  selector: 'app-integration-list',
  imports: [DatePipe, RouterLink, DeleteConfirmationDialogComponent, SkeletonComponent],
  templateUrl: './integration-list.component.html',
})
export class IntegrationListComponent extends IntegrationListBase<SlackIntegration> {
  protected readonly channel = 'slack';
  protected readonly label = 'Slack';

  constructor() {
    super();
    this.watch((resources: RealtimeResources) => resources.slack_integrations);
  }

  deleteConfirmationMessage(integration: SlackIntegration): string {
    return `Are you sure you want to delete Slack integration “${integration.name}”? Slack alerts from this integration will stop.`;
  }
}
