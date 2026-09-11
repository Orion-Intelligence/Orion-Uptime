import { E2E_NAME_PREFIX, HTTP_MONITORS_PATH, cleanupE2eHttpMonitors, createHttpMonitor, monitorCardById, testId, uniqueSuffix } from './controllers/shared.controller';

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
