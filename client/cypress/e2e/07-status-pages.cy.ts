import { E2E_NAME_PREFIX, HTTP_MONITORS_PATH, cleanupE2eHttpMonitors, deleteHttpMonitorViaUi, disableNoticeOverlay, monitorCardById, slugFor, testId, uniqueSuffix } from './controllers/shared.controller';
import { assertPublicStatusPage, cleanupE2eStatusPages, createStatusPage, deleteStatusPage } from './controllers/07-status-pages.controller';

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

describe('Status pages', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cleanupE2eStatusPages();
    cleanupE2eHttpMonitors();
  });

  it('publishes a monitor on a status page and serves it publicly', () => {
    const suffix = uniqueSuffix();
    const monitorName = `${E2E_NAME_PREFIX}HTTP status page ${suffix}`;
    const pageName = `${E2E_NAME_PREFIX}Status page ${suffix}`;
    const pageDescription = `Public availability for ${suffix}`;

    createHttpMonitor(monitorName).then((monitorId) => {
      createStatusPage(pageName, pageDescription, monitorName, monitorId).then((page) => {
        assertPublicStatusPage(page.slug, pageName, monitorName, monitorId);
        deleteStatusPage(page.id, pageName);
        deleteHttpMonitorViaUi(monitorId, monitorName);
      });
    });
  });
});

export {};
