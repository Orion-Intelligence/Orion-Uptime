import { DatePipe } from '@angular/common';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { IntegrationListBase } from '../../shared/base/integration-list.base';
import { EmailIntegration, RealtimeResources } from '../../shared/model/models';

@Component({
  selector: 'app-email-integration-list',
  imports: [DatePipe, RouterLink],
  templateUrl: './email-integration-list.component.html',
})
export class EmailIntegrationListComponent extends IntegrationListBase<EmailIntegration> {
  protected readonly channel = 'email';
  protected readonly label = 'Email';

  constructor() {
    super();
    this.watch((resources: RealtimeResources) => resources.email_integrations);
  }

  protected confirmMessage(integration: EmailIntegration): string {
    return `Delete “${integration.name}”? Email alerts to ${integration.email} will stop.`;
  }
}
