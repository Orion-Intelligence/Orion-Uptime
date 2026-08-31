import { DatePipe } from '@angular/common';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { IntegrationListBase } from '../../shared/base/integration-list.base';
import { RealtimeResources, SlackIntegration } from '../../shared/model/models';

@Component({
  selector: 'app-integration-list',
  imports: [DatePipe, RouterLink],
  templateUrl: './integration-list.component.html',
})
export class IntegrationListComponent extends IntegrationListBase<SlackIntegration> {
  protected readonly channel = 'slack';
  protected readonly label = 'Slack';

  constructor() {
    super();
    this.watch((resources: RealtimeResources) => resources.slack_integrations);
  }

  protected confirmMessage(integration: SlackIntegration): string {
    return `Delete “${integration.name}”? Slack alerts from this integration will stop.`;
  }
}
