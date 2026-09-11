import { testId } from './controllers/shared.controller';

describe('Dashboard', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  it('renders the health strip, metric tiles, activity, and incidents, and refreshes', () => {
    cy.visit('/dashboard');
    cy.get(testId('dashboard-main')).should('be.visible');

    cy.get(testId('dashboard-metrics')).should('be.visible');
    cy.get(testId('dashboard-total-monitors')).should('be.visible');
    cy.get(testId('dashboard-open-incidents')).should('be.visible');
    cy.get(testId('dashboard-slow-monitors')).should('be.visible');
    cy.get(testId('dashboard-average-response')).should('be.visible');

    cy.get(testId('dashboard-health-strip')).should('be.visible');
    cy.get(testId('dashboard-activity-panel')).should('be.visible');
    cy.get(testId('dashboard-incidents-panel')).should('be.visible');

    cy.get(testId('dashboard-refresh-button')).should('be.enabled').click();
    cy.get(testId('dashboard-metrics')).should('be.visible');
    cy.get(testId('dashboard-total-monitors')).should('be.visible');
  });
});

export {};
