import { E2E_NAME_PREFIX, cleanupE2eHttpMonitors, createHttpMonitor, deleteHttpMonitorViaUi, uniqueSuffix } from './controllers/shared.controller';
import { cleanupE2eIntegrations, createEmailIntegration, createSlackIntegration, deleteEmailIntegration, deleteSlackIntegration, openIntegrationsHub } from './controllers/05-integrations.controller';

describe('Integrations', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cleanupE2eIntegrations();
    cleanupE2eHttpMonitors();
  });

  it('assigns a monitor to a Slack and an Email integration, then removes everything', () => {
    const suffix = uniqueSuffix();
    const monitorName = `${E2E_NAME_PREFIX}HTTP integrations ${suffix}`;
    const slackName = `${E2E_NAME_PREFIX}Slack ${suffix}`;
    const emailName = `${E2E_NAME_PREFIX}Email ${suffix}`;

    createHttpMonitor(monitorName).then((monitorId) => {
      openIntegrationsHub();
      createSlackIntegration(slackName, monitorName, monitorId).then((slack) => {
        deleteSlackIntegration(slack.id, slack.name);
      });

      openIntegrationsHub();
      createEmailIntegration(emailName, monitorName, monitorId).then((email) => {
        deleteEmailIntegration(email.id, email.name);
      });

      deleteHttpMonitorViaUi(monitorId, monitorName);
    });
  });
});

export {};
