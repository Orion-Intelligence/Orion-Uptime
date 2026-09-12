import { cleanupE2eHttpMonitors, createHttpMonitor, disableNoticeOverlay, E2E_NAME_PREFIX, monitorCardById, testId, uniqueSuffix } from './controllers/shared.controller';

describe('Monitor list error handling', () => {
  let monitorId = '';

  beforeEach(() => {
    cy.loginAsAdmin();
    createHttpMonitor(`${E2E_NAME_PREFIX}Errors ${uniqueSuffix()}`).then((id) => {
      monitorId = id;
    });
    disableNoticeOverlay();
  });

  afterEach(() => {
    cleanupE2eHttpMonitors();
  });

  it('surfaces an error when deletion fails', () => {
    cy.intercept('DELETE', '**/api/HTTP_monitors/*/delete', { statusCode: 500, body: { success: false, message: 'Delete failed.' } }).as('deleteMonitor');
    monitorCardById(monitorId).find(testId('monitor-delete-button')).click();
    cy.get(testId('delete-confirmation-dialog')).should('be.visible');
    cy.get(testId('delete-confirmation-confirm')).click();
    cy.wait('@deleteMonitor');
    cy.get(testId('monitor-list-error')).should('be.visible');
  });

  it('surfaces an error when toggling active state fails', () => {
    cy.intercept('PUT', '**/api/HTTP_monitors/*/update', { statusCode: 500, body: { success: false, message: 'Update failed.' } }).as('updateMonitor');
    monitorCardById(monitorId).find(testId('monitor-toggle-active-button')).click();
    cy.wait('@updateMonitor');
    cy.get(testId('monitor-list-error')).should('be.visible');
  });

  it('surfaces an error when export fails', () => {
    cy.intercept('GET', '**/api/monitor-configs/**', { statusCode: 500, body: { success: false, message: 'Export failed.' } }).as('exportMonitor');
    monitorCardById(monitorId).find(testId('monitor-export-button')).click();
    cy.wait('@exportMonitor');
    cy.get(testId('monitor-list-error')).should('be.visible');
  });
});
