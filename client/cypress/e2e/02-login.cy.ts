describe('Orion Uptime - Login Session', () => {
  it('logs in as admin and signs out successfully', () => {
    cy.visit('/login');
    cy.get('[data-testid="login-page"]').should('be.visible');
    cy.docsScreenshot('login-page');

    cy.loginAsAdmin();
    cy.get('[data-testid="dashboard-main"]').should('be.visible');
    cy.docsScreenshot('dashboard');
    cy.get('[data-testid="profile-menu"]').click();
    cy.get('[data-testid="signout-btn"]').click({ scrollBehavior: false });
    cy.get('[data-testid="login-user"]').should('exist');
    cy.logout();
  });
});
