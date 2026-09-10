const testId = (id: string) => `[data-testid="${id}"]`;

const E2E_NAME_PREFIX = 'E2E ';
const HTTP_MONITORS_PATH = '/monitors/http';
const SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/T00000000/B00000000/e2eSlackWebhookToken';
const RECIPIENT_EMAIL = 'e2e-on-call@example.com';

const uniqueSuffix = () => `${Date.now()} ${Math.floor(Math.random() * 1_000_000)}`;

const slugFor = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');

const disableNoticeOverlay = () => {
  cy.document().then((doc) => {
    if (doc.getElementById('e2e-notice-overlay-style')) {
      return;
    }
    const style = doc.createElement('style');
    style.id = 'e2e-notice-overlay-style';
    style.textContent = `${testId('app-notification')} { pointer-events: none !important; }`;
    doc.head.appendChild(style);
  });
};

const monitorCardById = (id: string) => (
  cy.get(`${testId('monitor-detail-link')}[href="${HTTP_MONITORS_PATH}/${id}"]`).closest(testId('monitor-card'))
);

const slackCardById = (id: string) => (
  cy.get(`${testId('slack-integration-edit-link')}[href="/integrations/slack/${id}/edit"]`)
    .closest(testId('slack-integration-card'))
);

const emailRowById = (id: string) => (
  cy.get(`${testId('email-integration-edit-link')}[href="/integrations/email/${id}/edit"]`)
    .closest(testId('email-integration-row'))
);

const monitorIdByName = (name: string): Cypress.Chainable<string> => (
  cy.contains(testId('monitor-name'), name)
    .closest(testId('monitor-card'))
    .find(testId('monitor-detail-link'))
    .invoke('attr', 'href')
    .then((href) => {
      const id = String(href ?? '').split('/').pop() ?? '';
      expect(id, `${name} monitor ID`).to.not.equal('');
      return cy.wrap(id);
    })
);

const createHttpMonitor = (name: string): Cypress.Chainable<string> => {
  cy.visit(HTTP_MONITORS_PATH);
  cy.get(testId('resource-list-page')).should('be.visible');
  cy.get(testId('page-title')).should('contain.text', 'HTTP monitors');
  disableNoticeOverlay();

  cy.get(testId('new-monitor-button')).click();
  cy.get(testId('page-title')).should('contain.text', 'New HTTP monitor');
  cy.get(testId('monitor-name')).clear().type(name);
  cy.get(testId('monitor-url')).clear().type(`https://example.com/e2e-${slugFor(name)}`);
  cy.get(testId('monitor-expected-status')).clear().type('200');
  cy.get(testId('check-interval')).clear().type('60');
  cy.get(testId('timeout')).clear().type('10');
  cy.get(testId('expected-response-time')).clear().type('1000');

  cy.intercept('POST', '**/api/HTTP_monitors/create').as('createHttpMonitor');
  cy.get(testId('save-button')).click();
  cy.wait('@createHttpMonitor').its('response.statusCode').should('be.oneOf', [200, 201]);
  cy.location('pathname').should('eq', HTTP_MONITORS_PATH);

  return monitorIdByName(name);
};

const selectMonitorOption = (monitorName: string) => {
  cy.contains(testId('monitor-option-name'), monitorName)
    .closest(testId('monitor-option'))
    .click()
    .should('have.class', 'selected');
};

const assertIntegrationNameRequired = (createApi: string) => {
  const attempts = { count: 0 };
  cy.intercept('POST', createApi, () => { attempts.count += 1; });
  cy.get(testId('save-button')).click();
  cy.scrollTo('top', { ensureScrollable: false });
  cy.get(testId('integration-editor-error')).should('be.visible').and('contain.text', 'Integration name is required');
  cy.then(() => {
    expect(attempts.count, 'integration create requests while the name is blank').to.eq(0);
  });
};

const openIntegrationsHub = () => {
  cy.get(testId('nav-integrations')).click();
  cy.location('pathname').should('eq', '/integrations');
  cy.get(testId('integration-hub-page')).should('be.visible');
};

const createSlackIntegration = (name: string, monitorName: string, monitorId: string) => {
  cy.get(testId('integration-hub-slack')).click();
  cy.location('pathname').should('eq', '/integrations/slack');
  cy.get(testId('slack-integration-list-page')).should('be.visible');

  cy.get(testId('new-slack-integration-button')).click();
  cy.location('pathname').should('eq', '/integrations/slack/new');
  cy.get(testId('integration-editor-form')).should('be.visible');

  cy.get(testId('slack-webhook-url')).clear().type(SLACK_WEBHOOK_URL);
  assertIntegrationNameRequired('**/api/integrations/slack');

  cy.get(testId('integration-name')).clear().type(name);
  selectMonitorOption(monitorName);

  cy.intercept('POST', '**/api/integrations/slack').as('createSlackIntegration');
  cy.get(testId('save-button')).click();

  return cy.wait('@createSlackIntegration').then(({ request, response }) => {
    expect(response?.statusCode, 'slack create status').to.be.oneOf([200, 201]);
    expect(request.body.name, 'slack name sent').to.eq(name);
    expect(request.body.monitor_ids, 'slack monitor_ids sent').to.include(monitorId);

    const id = String(response?.body?.data?.id ?? '');
    expect(id, 'slack integration ID').to.not.equal('');
    cy.location('pathname').should('eq', '/integrations/slack');
    slackCardById(id).should('be.visible');
    slackCardById(id).find(testId('slack-integration-name')).should('have.text', name);
    slackCardById(id).should('contain.text', 'Assigned monitors · 1').and('contain.text', monitorName);
    return cy.wrap({ id, name: String(response?.body?.data?.name ?? name) });
  });
};

const deleteSlackIntegration = (id: string, name: string) => {
  slackCardById(id).find(testId('slack-integration-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-cancel')).click();
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  slackCardById(id).should('be.visible');

  cy.intercept('DELETE', '**/api/integrations/slack/*').as('deleteSlackIntegration');
  slackCardById(id).find(testId('slack-integration-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-confirm')).click();
  cy.wait('@deleteSlackIntegration').its('response.statusCode').should('eq', 200);
  cy.get(`${testId('slack-integration-edit-link')}[href="/integrations/slack/${id}/edit"]`).should('not.exist');
};

const createEmailIntegration = (name: string, monitorName: string, monitorId: string) => {
  cy.get(testId('integration-hub-email')).click();
  cy.location('pathname').should('eq', '/integrations/email');
  cy.get(testId('email-integration-list-page')).should('be.visible');

  cy.get(testId('new-email-integration-button')).click();
  cy.location('pathname').should('eq', '/integrations/email/new');
  cy.get(testId('integration-editor-form')).should('be.visible');

  cy.get(testId('recipient-email')).clear().type(RECIPIENT_EMAIL);
  assertIntegrationNameRequired('**/api/integrations/email');

  cy.get(testId('integration-name')).clear().type(name);
  selectMonitorOption(monitorName);

  cy.intercept('POST', '**/api/integrations/email').as('createEmailIntegration');
  cy.get(testId('save-button')).click();

  return cy.wait('@createEmailIntegration').then(({ request, response }) => {
    expect(response?.statusCode, 'email create status').to.be.oneOf([200, 201]);
    expect(request.body.name, 'email name sent').to.eq(name);
    expect(request.body.email, 'email recipient sent').to.eq(RECIPIENT_EMAIL);
    expect(request.body.monitor_ids, 'email monitor_ids sent').to.include(monitorId);

    const id = String(response?.body?.data?.id ?? '');
    expect(id, 'email integration ID').to.not.equal('');
    cy.location('pathname').should('eq', '/integrations/email');
    emailRowById(id).should('be.visible');
    emailRowById(id).find(testId('email-integration-name')).should('have.text', name);
    emailRowById(id).should('contain.text', '1 monitor').and('contain.text', monitorName);
    return cy.wrap({ id, name: String(response?.body?.data?.name ?? name) });
  });
};

const deleteEmailIntegration = (id: string, name: string) => {
  emailRowById(id).find(testId('email-integration-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-cancel')).click();
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  emailRowById(id).should('be.visible');

  cy.intercept('DELETE', '**/api/integrations/email/*').as('deleteEmailIntegration');
  emailRowById(id).find(testId('email-integration-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-confirm')).click();
  cy.wait('@deleteEmailIntegration').its('response.statusCode').should('eq', 200);
  cy.get(`${testId('email-integration-edit-link')}[href="/integrations/email/${id}/edit"]`).should('not.exist');
};

const deleteHttpMonitor = (id: string, name: string) => {
  cy.get(testId('nav-http')).click();
  cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
  cy.get(testId('resource-list-page')).should('be.visible');

  cy.intercept('DELETE', '**/api/HTTP_monitors/*/delete').as('deleteHttpMonitor');
  monitorCardById(id).find(testId('monitor-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-confirm')).click();
  cy.wait('@deleteHttpMonitor').its('response.statusCode').should('eq', 200);
  cy.get(`${testId('monitor-detail-link')}[href="${HTTP_MONITORS_PATH}/${id}"]`).should('not.exist');
};

describe('Integrations', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cy.request({ url: '/api/integrations/slack', failOnStatusCode: false }).then((response) => {
      const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
      rows.filter(row => String(row.name).startsWith(E2E_NAME_PREFIX)).forEach((row) => {
        cy.request({ method: 'DELETE', url: `/api/integrations/slack/${row.id}`, failOnStatusCode: false });
      });
    });
    cy.request({ url: '/api/integrations/email', failOnStatusCode: false }).then((response) => {
      const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
      rows.filter(row => String(row.name).startsWith(E2E_NAME_PREFIX)).forEach((row) => {
        cy.request({ method: 'DELETE', url: `/api/integrations/email/${row.id}`, failOnStatusCode: false });
      });
    });
    cy.request({ url: '/api/HTTP_monitors/list_all', failOnStatusCode: false }).then((response) => {
      const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
      rows.filter(row => String(row.name).startsWith(E2E_NAME_PREFIX)).forEach((row) => {
        cy.request({ method: 'DELETE', url: `/api/HTTP_monitors/${row.id}/delete`, failOnStatusCode: false });
      });
    });
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

      deleteHttpMonitor(monitorId, monitorName);
    });
  });
});

export {};
