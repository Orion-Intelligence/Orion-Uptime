export const testId = (id: string) => `[data-testid="${id}"]`;

export const E2E_NAME_PREFIX = 'E2E ';
export const HTTP_MONITORS_PATH = '/monitors/http';
export const HTTP_MONITORS_LIST_API = '/api/HTTP_monitors/list_all';

export const uniqueSuffix = () => `${Date.now()} ${Math.floor(Math.random() * 1_000_000)}`;

export const slugFor = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');

export const disableNoticeOverlay = () => {
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

export const monitorCardById = (id: string) => (
  cy.get(`${testId('monitor-detail-link')}[href="${HTTP_MONITORS_PATH}/${id}"]`).closest(testId('monitor-card'))
);

export const monitorIdByName = (name: string): Cypress.Chainable<string> => (
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

export const createHttpMonitor = (name: string): Cypress.Chainable<string> => {
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

export const deleteHttpMonitorViaUi = (id: string, name: string) => {
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

export const cleanupE2eByName = (listUrl: string, deleteUrl: (id: string) => string) => {
  cy.request({ url: listUrl, failOnStatusCode: false }).then((response) => {
    const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
    rows
      .filter(row => String(row.name).startsWith(E2E_NAME_PREFIX))
      .forEach((row) => {
        cy.request({ method: 'DELETE', url: deleteUrl(row.id), failOnStatusCode: false });
      });
  });
};

export const cleanupE2eHttpMonitors = () => (
  cleanupE2eByName(HTTP_MONITORS_LIST_API, (id) => `/api/HTTP_monitors/${id}/delete`)
);
