import { cleanupE2eHttpMonitors, createHttpMonitor, E2E_NAME_PREFIX, testId, uniqueSuffix } from './controllers/shared.controller';

describe('Monitor detail history ranges', () => {
  let monitorId = '';

  beforeEach(() => {
    cy.loginAsAdmin();
    createHttpMonitor(`${E2E_NAME_PREFIX}Detail ${uniqueSuffix()}`).then((id) => {
      monitorId = id;
    });
  });

  afterEach(() => {
    cleanupE2eHttpMonitors();
  });

  it('reloads status and response history when a range is selected', () => {
    const requested: string[] = [];
    cy.intercept('GET', '**/api/dashboard/status-history/**', (req) => {
      requested.push(req.url);
    });
    cy.intercept('GET', '**/api/dashboard/response-history/**', (req) => {
      requested.push(req.url);
    });

    cy.visit(`/monitors/http/${monitorId}`);
    cy.get(testId('monitor-detail-page')).should('be.visible');

    cy.get(testId('monitor-detail-status-chart')).contains('button', 'Month').click();
    cy.get(testId('monitor-detail-response-chart')).contains('button', 'Year').click();

    cy.wrap(requested).should((urls) => {
      expect(urls.some((url) => url.includes('status-history') && url.includes('days=30')), 'status history days=30 requested').to.equal(true);
      expect(urls.some((url) => url.includes('response-history') && url.includes('days=365')), 'response history days=365 requested').to.equal(true);
    });
  });

  it('shows an error when the initial history request fails', () => {
    cy.intercept('GET', '**/api/dashboard/status-history/**', { statusCode: 500, body: { success: false, message: 'History unavailable.' } }).as('statusFail');
    cy.visit(`/monitors/http/${monitorId}`);
    cy.get(testId('monitor-detail-error')).should('be.visible');
  });
});
