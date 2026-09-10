const testId = (id: string) => `[data-testid="${id}"]`;

const HTTP_MONITORS_PATH = '/monitors/http';
const STATUS_PAGES_PATH = '/status-pages';
const E2E_NAME_PREFIX = 'E2E ';

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

const statusPageCardById = (id: string) => (
  cy.get(`${testId('status-page-edit-link')}[href="${STATUS_PAGES_PATH}/${id}/edit"]`)
    .closest(testId('status-page-card'))
);

const createHttpMonitor = (name: string): Cypress.Chainable<string> => {
  cy.visit(HTTP_MONITORS_PATH);
  cy.get(testId('resource-list-page')).should('be.visible');
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

  cy.intercept('POST', '**/api/HTTP_monitors/create').as('createHttpMonitor');
  cy.get(testId('save-button')).click();

  return cy.wait('@createHttpMonitor').then(({ response }) => {
    expect(response?.statusCode, 'monitor create status').to.be.oneOf([200, 201]);
    const id = String(response?.body?.data?.id ?? '');
    expect(id, 'created monitor ID').to.not.equal('');
    cy.location('pathname').should('eq', HTTP_MONITORS_PATH);
    return cy.wrap(id);
  });
};

const assertStatusPageValidation = () => {
  const attempts = { count: 0 };
  cy.intercept('POST', '**/api/status-pages', () => { attempts.count += 1; });
  cy.get(testId('save-button')).click();
  cy.scrollTo('top', { ensureScrollable: false });
  cy.get(testId('status-page-editor-error')).should('be.visible').and('contain.text', 'Name is required');
  cy.location('pathname').should('eq', `${STATUS_PAGES_PATH}/new`);
  cy.then(() => {
    expect(attempts.count, 'create requests while the form is invalid').to.eq(0);
  });
};

const createStatusPage = (name: string, description: string, monitorName: string, monitorId: string) => {
  cy.get(testId('nav-status-pages')).click();
  cy.location('pathname').should('eq', STATUS_PAGES_PATH);
  cy.get(testId('status-page-list-page')).should('be.visible');
  disableNoticeOverlay();

  cy.get(testId('new-status-page-button')).click();
  cy.location('pathname').should('eq', `${STATUS_PAGES_PATH}/new`);
  cy.get(testId('status-page-editor-form')).should('be.visible');

  assertStatusPageValidation();

  cy.get(testId('status-page-name-input')).should('have.value', '');
  cy.get(testId('status-page-name-input')).type(name);
  cy.get(testId('status-page-description')).type(description);
  cy.contains(testId('monitor-option-name'), monitorName)
    .closest(testId('monitor-option'))
    .click()
    .should('have.class', 'selected');

  cy.intercept('POST', '**/api/status-pages').as('createStatusPage');
  cy.get(testId('save-button')).click();

  return cy.wait('@createStatusPage').then(({ request, response }) => {
    expect(response?.statusCode, 'status page create status').to.be.oneOf([200, 201]);
    expect(request.body.name, 'status page name sent').to.eq(name);
    expect(request.body.monitor_ids, 'status page monitor_ids sent').to.include(monitorId);

    const data = response?.body?.data as { id: string; name: string; slug: string; public_path: string };
    expect(String(data?.id ?? ''), 'status page ID').to.not.equal('');
    expect(String(data?.slug ?? ''), 'status page slug').to.not.equal('');

    cy.location('pathname').should('eq', STATUS_PAGES_PATH);
    disableNoticeOverlay();
    statusPageCardById(data.id).should('be.visible');
    statusPageCardById(data.id).find(testId('status-page-name')).should('have.text', name);
    statusPageCardById(data.id).should('contain.text', description);
    statusPageCardById(data.id).should('contain.text', 'Included monitors · 1').and('contain.text', monitorName);
    statusPageCardById(data.id).should('contain.text', `/status/${data.slug}`);
    statusPageCardById(data.id).find(testId('status-page-public-link')).should('have.attr', 'href', data.public_path);

    return cy.wrap(data);
  });
};

const assertPublicStatusPage = (slug: string, name: string, monitorName: string, monitorId: string) => {
  cy.visit(`/status/${slug}`);

  cy.get(testId('public-status-page')).should('be.visible');
  cy.get(testId('public-status-header')).should('be.visible');
  cy.get(testId('public-status-last-updated')).should('contain.text', 'Last updated');
  cy.get(testId('public-status-overall')).should('be.visible');
  cy.get(testId('public-status-dot')).should('be.visible');
  cy.get(testId('public-status-error')).should('not.exist');

  cy.get(testId('public-status-services')).should('be.visible');
  cy.get(testId('monitor-group')).should('have.length', 1);
  cy.get(testId('monitor-group-label')).should('be.visible');
  cy.get(testId('public-status-empty')).should('not.exist');

  cy.get(testId('public-monitor-row')).should('have.length', 1);
  cy.get(testId('public-monitor-row')).first().within(() => {
    cy.get(testId('public-monitor-link')).should('contain.text', monitorName);
    cy.get(testId('public-monitor-uptime-bars')).should('exist');
    cy.get(testId('public-monitor-status')).should('be.visible');
    cy.get(testId('public-monitor-uptime')).should('be.visible');
  });

  cy.get(testId('public-status-uptime-summary')).should('be.visible');
  cy.get(testId('public-status-uptime-window')).should('have.length', 4);

  cy.get(testId('public-monitor-link')).first().click();
  cy.location('pathname').should('eq', `/status/${slug}/${monitorId}`);
  cy.get(testId('public-monitor-detail-page')).should('be.visible');
  cy.get(testId('public-monitor-name')).should('contain.text', monitorName);
  cy.get(testId('public-monitor-type')).should('contain.text', 'HTTP');
  cy.get(testId('public-monitor-summary')).should('be.visible');
  cy.get(testId('public-monitor-status')).should('be.visible');
  cy.get(testId('public-monitor-availability')).should('be.visible');
  cy.get(testId('public-monitor-uptime-bars')).should('exist');
  cy.get(testId('public-monitor-uptime-window')).should('have.length', 4);
  cy.get(testId('public-monitor-response')).should('be.visible');
  cy.get(testId('public-monitor-events')).scrollIntoView().should('be.visible');
  cy.get(testId('public-monitor-error')).should('not.exist');

  cy.get(testId('public-monitor-back')).click();
  cy.location('pathname').should('eq', `/status/${slug}`);
  cy.get(testId('public-status-overall')).should('be.visible');
  cy.contains(testId('public-monitor-link'), monitorName).should('be.visible');
  void name;
};

const deleteStatusPage = (id: string, name: string) => {
  cy.visit(STATUS_PAGES_PATH);
  cy.get(testId('status-page-list-page')).should('be.visible');
  disableNoticeOverlay();

  statusPageCardById(id).find(testId('status-page-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-cancel')).click();
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  statusPageCardById(id).should('be.visible');

  cy.intercept('DELETE', '**/api/status-pages/*').as('deleteStatusPage');
  statusPageCardById(id).find(testId('status-page-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-confirm')).click();
  cy.wait('@deleteStatusPage').its('response.statusCode').should('eq', 200);
  cy.get(`${testId('status-page-edit-link')}[href="${STATUS_PAGES_PATH}/${id}/edit"]`).should('not.exist');
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

describe('Status pages', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cy.request({ url: '/api/status-pages', failOnStatusCode: false }).then((response) => {
      const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
      rows.filter(row => String(row.name).startsWith(E2E_NAME_PREFIX)).forEach((row) => {
        cy.request({ method: 'DELETE', url: `/api/status-pages/${row.id}`, failOnStatusCode: false });
      });
    });
    cy.request({ url: '/api/HTTP_monitors/list_all', failOnStatusCode: false }).then((response) => {
      const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
      rows.filter(row => String(row.name).startsWith(E2E_NAME_PREFIX)).forEach((row) => {
        cy.request({ method: 'DELETE', url: `/api/HTTP_monitors/${row.id}/delete`, failOnStatusCode: false });
      });
    });
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
        deleteHttpMonitor(monitorId, monitorName);
      });
    });
  });
});

export {};
