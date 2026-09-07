const HTTP_MONITORS_PATH = '/monitors/http';
const IMPORT_FIXTURE_PATH = 'src/assets/cypress data/04-http-monitor-import.json';

const newMonitorName = (scenario: string) => (
  `E2E HTTP ${scenario} ${Date.now()} ${Math.floor(Math.random() * 1_000_000)}`
);

const cardFor = (name: string) => cy.contains('article.resource-card', name);

const cardForId = (id: string) => (
  cy.get(`a[href="${HTTP_MONITORS_PATH}/${id}"]`).closest('article.resource-card')
);

const monitorUrl = (name: string) => (
  `https://example.com/e2e-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
);

const visitHttpMonitors = () => {
  cy.loginAsAdmin();
  cy.visit(HTTP_MONITORS_PATH);
  cy.get('h1').should('contain.text', 'HTTP monitors');
};

const createHttpMonitor = (name: string) => {
  cy.contains('a', 'New monitor').click();
  cy.location('pathname').should('eq', `${HTTP_MONITORS_PATH}/new`);

  cy.get('#name').clear().type(name);
  cy.get('#url').clear().type(monitorUrl(name));
  cy.get('#interval').clear().type('60');
  cy.get('#timeout').clear().type('10');
  cy.get('#status').clear().type('200');
  cy.get('#response-time').clear().type('1000');

  cy.intercept('POST', '**/api/HTTP_monitors/create').as('createHttpMonitor');
  cy.contains('button', 'Create').click();
  cy.wait('@createHttpMonitor').its('response.statusCode').should('be.oneOf', [200, 201]);
  cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
  cardFor(name).should('be.visible');
};

const deleteHttpMonitor = (name: string) => {
  cy.intercept('DELETE', '**/api/HTTP_monitors/*/delete').as('deleteHttpMonitor');
  cardFor(name).find(`button[aria-label="Delete ${name}"]`).click();
  cy.get('[data-testid="delete-confirmation-dialog"]').should('contain.text', name);
  cy.get('[data-testid="delete-confirmation-confirm"]').click();
  cy.wait('@deleteHttpMonitor').its('response.statusCode').should('eq', 200);
  cardFor(name).should('not.exist');
};

const deleteHttpMonitorById = (id: string) => {
  cy.request('DELETE', `/api/HTTP_monitors/${id}/delete`)
    .its('status')
    .should('eq', 200);
};

describe('HTTP monitor management', () => {
  it('creates and deletes an HTTP monitor', () => {
    const name = newMonitorName('create delete');

    visitHttpMonitors();
    createHttpMonitor(name);
    deleteHttpMonitor(name);
  });

  it('edits an HTTP monitor after creating it', () => {
    const name = newMonitorName('edit');
    const updatedName = `${name} updated`;

    visitHttpMonitors();
    createHttpMonitor(name);

    cardFor(name).find(`a[aria-label="Edit ${name}"]`).click();
    cy.get('#name').clear().type(updatedName);
    cy.get('#interval').clear().type('120');
    cy.get('#timeout').clear().type('15');
    cy.get('#response-time').clear().type('1500');

    cy.intercept('PUT', '**/api/HTTP_monitors/*/update').as('updateHttpMonitor');
    cy.contains('button', 'Save changes').click();
    cy.wait('@updateHttpMonitor').its('response.statusCode').should('eq', 200);
    cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
    cardFor(updatedName).should('be.visible');
    deleteHttpMonitor(updatedName);
  });

  it('pauses and starts an HTTP monitor', () => {
    const name = newMonitorName('pause start');

    visitHttpMonitors();
    createHttpMonitor(name);

    cy.intercept('PUT', '**/api/HTTP_monitors/*/update').as('pauseHttpMonitor');
    cardFor(name).find(`button[aria-label="Pause ${name}"]`).click();
    cy.wait('@pauseHttpMonitor').its('response.statusCode').should('eq', 200);
    cardFor(name).find(`button[aria-label="Start ${name}"]`).should('be.visible');

    cy.intercept('PUT', '**/api/HTTP_monitors/*/update').as('startHttpMonitor');
    cardFor(name).find(`button[aria-label="Start ${name}"]`).click();
    cy.wait('@startHttpMonitor').its('response.statusCode').should('eq', 200);
    cardFor(name).find(`button[aria-label="Pause ${name}"]`).should('be.visible');
    deleteHttpMonitor(name);
  });

  it('imports an HTTP monitor configuration and exports it', () => {
    visitHttpMonitors();

    cy.intercept('POST', '**/api/monitor-configs/import*').as('importHttpMonitor');
    cy.get('input[type="file"]').selectFile(IMPORT_FIXTURE_PATH, { force: true });
    cy.wait('@importHttpMonitor').then(({ response }) => {
      expect(response?.statusCode).to.be.oneOf([200, 201]);
      const monitorId = String(response?.body?.data?.monitor_id ?? '');
      expect(monitorId, 'imported monitor ID').to.not.equal('');
      cy.wrap(monitorId).as('importedHttpMonitorId');
      cardForId(monitorId).should('be.visible');
    });

    cy.get('@importedHttpMonitorId').then((monitorId) => {
      const id = String(monitorId);
      cy.intercept('GET', `**/api/monitor-configs/HTTP/${id}`).as('exportHttpMonitor');
      cardForId(id).find('button[aria-label^="Export "]').click();
      cy.wait('@exportHttpMonitor').then(({ response }) => {
        expect(response?.statusCode).to.equal(200);
        expect(response?.body?.data?.monitor_id).to.equal(id);
        expect(response?.body?.data?.monitor_type).to.equal('HTTP');
      });
      deleteHttpMonitorById(id);
    });
  });

  it('opens an HTTP monitor detail page and returns to the list', () => {
    const name = newMonitorName('details');

    visitHttpMonitors();
    createHttpMonitor(name);

    cardFor(name).find(`a[title="${name}"]`).click();
    cy.location('pathname').should('match', /^\/monitors\/http\/[^/]+$/);
    cy.get('h1').should('contain.text', name);
    cy.contains('a', 'Back to list').click();
    cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
    deleteHttpMonitor(name);
  });
});
