describe('Monitor list navigation', () => {
  it('opens every route that uses the shared monitor list', () => {
    cy.loginAsAdmin();

    const routes = [
      ['/monitors/http', 'HTTP monitors'],
      ['/monitors/api', 'API monitors'],
      ['/monitors/ping', 'Ping monitors'],
      ['/monitors/heartbeat', 'Heartbeat monitors'],
      ['/auth-profiles', 'Auth profiles'],
    ];

    for (const [path, heading] of routes) {
      cy.visit(path);
      cy.location('pathname').should('eq', path);
      cy.get('h1').should('contain.text', heading);
    }
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
