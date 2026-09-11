import { testId } from './shared.controller';

export const SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/T00000000/B00000000/e2eSlackWebhookToken';
export const RECIPIENT_EMAIL = 'e2e-on-call@example.com';

export const slackCardById = (id: string) => (
  cy.get(`${testId('slack-integration-edit-link')}[href="/integrations/slack/${id}/edit"]`)
    .closest(testId('slack-integration-card'))
);

export const emailRowById = (id: string) => (
  cy.get(`${testId('email-integration-edit-link')}[href="/integrations/email/${id}/edit"]`)
    .closest(testId('email-integration-row'))
);

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

export const openIntegrationsHub = () => {
  cy.get(testId('nav-integrations')).click();
  cy.location('pathname').should('eq', '/integrations');
  cy.get(testId('integration-hub-page')).should('be.visible');
};

export const createSlackIntegration = (name: string, monitorName: string, monitorId: string) => {
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

export const deleteSlackIntegration = (id: string, name: string) => {
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

export const createEmailIntegration = (name: string, monitorName: string, monitorId: string) => {
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

export const deleteEmailIntegration = (id: string, name: string) => {
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

export const cleanupE2eIntegrations = () => {
  cy.request({ url: '/api/integrations/slack', failOnStatusCode: false }).then((response) => {
    const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
    rows.filter(row => String(row.name).startsWith('E2E ')).forEach((row) => {
      cy.request({ method: 'DELETE', url: `/api/integrations/slack/${row.id}`, failOnStatusCode: false });
    });
  });
  cy.request({ url: '/api/integrations/email', failOnStatusCode: false }).then((response) => {
    const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
    rows.filter(row => String(row.name).startsWith('E2E ')).forEach((row) => {
      cy.request({ method: 'DELETE', url: `/api/integrations/email/${row.id}`, failOnStatusCode: false });
    });
  });
};
