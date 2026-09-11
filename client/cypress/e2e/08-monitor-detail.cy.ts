import { E2E_NAME_PREFIX, HTTP_MONITORS_PATH, cleanupE2eHttpMonitors, disableNoticeOverlay, monitorCardById, slugFor, testId, uniqueSuffix } from './controllers/shared.controller';

const createHttpMonitor = (name: string): Cypress.Chainable<string> => {
  cy.visit(HTTP_MONITORS_PATH);
  cy.get(testId('resource-list-page')).should('be.visible');
  cy.get(testId('page-title')).should('contain.text', 'HTTP monitors');
  disableNoticeOverlay();

  cy.get(testId('new-monitor-button')).click();
  cy.location('pathname').should('eq', `${HTTP_MONITORS_PATH}/new`);
  cy.get(testId('resource-editor-form')).should('be.visible');
  cy.get(testId('page-title')).should('contain.text', 'New HTTP monitor');
  cy.get(testId('monitor-name')).clear().type(name);
  cy.get(testId('monitor-url')).clear().type(`https://example.com/e2e-${slugFor(name)}`);
  cy.get(testId('monitor-expected-status')).clear().type('200');
  cy.get(testId('check-interval')).clear().type('60');
  cy.get(testId('timeout')).clear().type('10');
  cy.get(testId('expected-response-time')).clear().type('1000');

  cy.intercept('POST', '**/api/HTTP_monitors/create').as('createHttpMonitor');
  cy.get(testId('save-button')).click();

  return cy.wait('@createHttpMonitor').then(({ response }) => {
    expect(response?.statusCode, 'monitor create status').to.be.oneOf([200, 201]);
    const id = String(response?.body?.data?.id ?? '');
    expect(id, 'created monitor ID').to.not.equal('');
    cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
    monitorCardById(id).should('be.visible');
    return cy.wrap(id);
  });
};

describe('Monitor detail', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cleanupE2eHttpMonitors();
  });

  it('opens a monitor detail page and renders summary, charts, and incident history', () => {
    const name = `${E2E_NAME_PREFIX}detail ${uniqueSuffix()}`;

    createHttpMonitor(name).then((id) => {
      monitorCardById(id).find(testId('monitor-detail-link')).click();
      cy.location('pathname').should('eq', `${HTTP_MONITORS_PATH}/${id}`);

      cy.get(testId('monitor-detail-page')).should('be.visible');
      cy.get(testId('monitor-detail-name')).should('contain.text', name);

      cy.get(testId('monitor-detail-summary')).should('be.visible').and('contain.text', 'Uptime');
      cy.get(testId('monitor-detail-status')).should('be.visible');
      cy.get(testId('monitor-detail-status-chart')).should('be.visible').and('contain.text', 'Status over time');
      cy.get(testId('monitor-detail-response-chart')).should('be.visible').and('contain.text', 'Response time');
      cy.get(testId('incident-history')).should('be.visible').and('contain.text', 'Incident history');

      cy.get(testId('monitor-detail-back')).click();
      cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
      cy.get(testId('resource-list-page')).should('be.visible');
    });
  });
});

export {};
