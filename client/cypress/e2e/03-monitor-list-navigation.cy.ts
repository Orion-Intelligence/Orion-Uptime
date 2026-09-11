import { testId } from './controllers/shared.controller';

const systemLogPage = {
  success: true,
  message: 'System logs retrieved successfully.',
  data: {
    logs: [
      { type: 'WARNING', time: '10/09/2026 09:36:15', file: 'log_1.log', source: 'ProfileManager (/app/orion/api/interactive/profile_manager/profile_manager.py:229)', message: 'Session file unreadable' },
      { type: 'ERROR', time: '10/09/2026 09:35:43', file: 'log_1.log', source: 'elastic_controller (/app/orion/services/elastic_manager/elastic_controller.py:443)', message: 'ELASTIC : Something unexpected happened' },
      { type: 'INFO', time: '10/09/2026 09:30:01', file: 'log_2.log', source: 'boot (/app/main.py:1)', message: 'Service started' },
    ],
    page: 1,
    limit: 200,
    total: 3,
    has_more: false,
    source_profile_name: 'orion test',
  },
};

describe('Monitor list navigation', () => {
  it('opens every sidebar tab and verifies each page', () => {
    cy.intercept('GET', '**/api/system-logs*', systemLogPage).as('systemLogs');
    cy.loginAsAdmin();
    cy.visit('/dashboard');

    cy.get(testId('nav-dashboard')).click();
    cy.location('pathname').should('eq', '/dashboard');
    cy.get(testId('dashboard-main')).should('be.visible');

    const listTabs: Array<[string, string, string]> = [
      ['nav-http', '/monitors/http', 'HTTP monitors'],
      ['nav-api', '/monitors/api', 'API monitors'],
      ['nav-ping', '/monitors/ping', 'Ping monitors'],
      ['nav-heartbeat', '/monitors/heartbeat', 'Heartbeat monitors'],
      ['nav-auth-profiles', '/auth-profiles', 'Auth profiles'],
    ];

    for (const [nav, path, heading] of listTabs) {
      cy.get(testId(nav)).click();
      cy.location('pathname').should('eq', path);
      cy.get(testId('resource-list-page')).should('be.visible');
      cy.get(testId('page-title')).should('contain.text', heading);
    }

    cy.get(testId('nav-status-pages')).click();
    cy.location('pathname').should('eq', '/status-pages');
    cy.get(testId('status-page-list-page')).should('be.visible');
    cy.get('h1').should('contain.text', 'Status pages');

    cy.get(testId('nav-integrations')).click();
    cy.location('pathname').should('eq', '/integrations');
    cy.get(testId('integration-hub-page')).should('be.visible');
    cy.get(testId('integration-hub-slack')).should('be.visible');
    cy.get(testId('integration-hub-email')).should('be.visible');

    cy.get(testId('nav-users')).click();
    cy.location('pathname').should('eq', '/users');
    cy.get(testId('user-list-page')).should('be.visible');
    cy.get('h1').should('contain.text', 'Registered users');

    cy.get(testId('nav-log-manager')).click();
    cy.location('pathname').should('eq', '/log-manager');
    cy.wait('@systemLogs').then(({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get('page'), 'first page requested').to.eq('1');
      expect(url.searchParams.get('limit'), 'page size requested').to.eq('200');
    });
    cy.get(testId('log-manager-page')).should('be.visible');
    cy.get(testId('page-title')).should('contain.text', 'Log Manager');
    cy.get(testId('log-type-filter')).should('be.visible').find('option').should('have.length', 4);
    cy.get(testId('log-date-range')).should('be.visible').and('contain.text', 'Select date range');
    cy.get(testId('log-refresh-button')).should('be.visible');
    cy.get(testId('log-table')).find('thead th').should('have.length', 5);
    cy.get(testId('log-table')).find('thead th').eq(0).should('contain.text', 'Type');
    cy.get(testId('log-table')).find('thead th').eq(4).should('contain.text', 'Message');
    cy.get(testId('log-row')).should('have.length', 3);
    cy.get(testId('log-type-pill')).eq(0).should('have.class', 'warning');
    cy.get(testId('log-type-pill')).eq(1).should('have.class', 'error');
    cy.get(testId('log-type-pill')).eq(2).should('have.class', 'info');
    cy.get(testId('log-time')).first().should('contain.text', '10/09/2026 09:36:15');
    cy.get(testId('log-file')).first().should('contain.text', 'log_1.log');
    cy.get(testId('log-source')).first().should('contain.text', 'ProfileManager');
    cy.get(testId('log-page-number')).should('contain.text', 'Page 1');
    cy.get(testId('log-page-previous')).should('not.exist');
    cy.get(testId('log-page-next')).should('not.exist');
    cy.get(testId('log-refresh-button')).click();
    cy.wait('@systemLogs');
    cy.get(testId('log-row')).should('have.length', 3);
  });

  it('rejects a configuration for a different monitor tab', () => {
    cy.loginAsAdmin();
    cy.visit('/monitors/http');
    cy.contains('button', 'Import file').should('be.visible');

    let importRequests = 0;
    cy.intercept('POST', '**/api/monitor-configs/import*', () => {
      importRequests += 1;
    });
    cy.get('input[type="file"]').selectFile({
      contents: Cypress.Buffer.from(JSON.stringify({
        monitor_type: 'API',
        name: 'Wrong tab',
        url: 'https://example.com/api',
        expected_status_code: 200,
        check_interval: 60,
        timeout: 10,
      })),
      fileName: 'api-monitor.json',
      mimeType: 'application/json',
    }, { force: true });

    cy.get('[role="alert"]').should('contain.text', 'API monitor cannot be imported from the HTTP monitor tab.');
    cy.contains('button', 'Import file').should('be.enabled');
    cy.then(() => {
      expect(importRequests).to.equal(0);
    });
  });

});

export {};
