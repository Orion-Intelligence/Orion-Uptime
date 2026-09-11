import { testId } from './controllers/shared.controller';
import { LogEntryStub, SYSTEM_LOGS_API, buildLogPage, openLogManager, searchParam } from './controllers/10-log-manager.controller';

const FIRST_PAGE: LogEntryStub[] = [
  { type: 'WARNING', time: '10/09/2026 09:36:15', file: 'log_1.log', source: 'ProfileManager (/app/orion/api/interactive/profile_manager/profile_manager.py:229)', message: 'Session file unreadable' },
  { type: 'ERROR', time: '10/09/2026 09:35:43', file: 'log_1.log', source: 'elastic_controller (/app/orion/services/elastic_manager/elastic_controller.py:443)', message: 'ELASTIC : Something unexpected happened' },
  { type: 'DEBUG', time: '10/09/2026 09:30:01', file: 'log_2.log', source: 'boot (/app/main.py:1)', message: 'Service started' },
];

const SECOND_PAGE: LogEntryStub[] = [
  { type: 'trace', time: '10/08/2026 22:11:04', file: 'log_9.log', source: 'scheduler (/app/worker.py:12)', message: 'Second page entry' },
];

describe('Log Manager', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  it('filters by type, paginates, and selects a date range', () => {
    cy.intercept('GET', SYSTEM_LOGS_API, (req) => {
      req.reply(Number(searchParam(req.url, 'page') ?? '1') > 1 ? buildLogPage(2, SECOND_PAGE, false) : buildLogPage(1, FIRST_PAGE, true));
    }).as('systemLogs');

    cy.visit('/dashboard');
    openLogManager();

    cy.wait('@systemLogs').then(({ request }) => {
      expect(searchParam(request.url, 'page'), 'initial page').to.eq('1');
      expect(searchParam(request.url, 'limit'), 'page size').to.eq('200');
    });
    cy.get(testId('log-row')).should('have.length', 3);
    cy.get(testId('log-source-profile')).should('contain.text', 'orion test');
    cy.get(testId('log-type-pill')).eq(0).should('have.class', 'warning');
    cy.get(testId('log-type-pill')).eq(1).should('have.class', 'error');
    cy.get(testId('log-type-pill')).eq(2).should('have.class', 'info');

    cy.get(testId('log-type-filter')).select('error');
    cy.wait('@systemLogs').then(({ request }) => {
      expect(searchParam(request.url, 'log_type'), 'type filter applied').to.eq('ERROR');
      expect(searchParam(request.url, 'page'), 'filter resets to first page').to.eq('1');
    });

    cy.get(testId('log-page-next')).click();
    cy.wait('@systemLogs').then(({ request }) => {
      expect(searchParam(request.url, 'page'), 'advances to next page').to.eq('2');
    });
    cy.get(testId('log-page-number')).should('contain.text', 'Page 2');
    cy.get(testId('log-row')).should('have.length', 1);
    cy.get(testId('log-type-pill')).first().should('have.class', 'unknown');
    cy.get(testId('log-page-next')).should('not.exist');

    cy.get(testId('log-page-previous')).click();
    cy.wait('@systemLogs').then(({ request }) => {
      expect(searchParam(request.url, 'page'), 'returns to first page').to.eq('1');
    });
    cy.get(testId('log-page-number')).should('contain.text', 'Page 1');

    cy.get(testId('log-date-range')).click();
    cy.get(testId('log-calendar')).should('be.visible');
    cy.get(testId('log-calendar-next')).should('not.exist');
    cy.get(testId('log-calendar-previous')).click();
    cy.get(testId('log-calendar-next')).should('be.visible');
    cy.get(testId('log-calendar-next')).click();
    cy.get(testId('log-calendar-next')).should('not.exist');
    cy.get(testId('log-calendar-previous')).click();

    const enabledDay = (label: RegExp) => cy.contains(`${testId('log-calendar-day')}:not([disabled]):not(.faded)`, label);
    enabledDay(/^15$/).click();
    enabledDay(/^13$/).click();
    enabledDay(/^22$/).click();
    cy.wait('@systemLogs').then(({ request }) => {
      expect(searchParam(request.url, 'date_from'), 'range start').to.match(/^\d{4}-\d{2}-13$/);
      expect(searchParam(request.url, 'date_to'), 'range end').to.match(/^\d{4}-\d{2}-22$/);
    });
    cy.get(testId('log-date-range')).should('not.contain.text', 'Select date range');
    cy.get(testId('log-calendar')).should('not.exist');

    cy.get(testId('log-date-range')).click();
    cy.get(testId('log-calendar-clear')).click();
    cy.wait('@systemLogs').then(({ request }) => {
      expect(searchParam(request.url, 'date_from'), 'range cleared').to.eq(null);
    });
    cy.get(testId('log-date-range')).should('contain.text', 'Select date range');

    cy.get(testId('log-date-range')).click();
    cy.get(testId('log-calendar')).should('be.visible');
    cy.get(testId('page-title')).click();
    cy.get(testId('log-calendar')).should('not.exist');

    cy.get(testId('log-date-range')).click();
    cy.get(testId('log-calendar')).should('be.visible');
    cy.get('body').type('{esc}');
    cy.get(testId('log-calendar')).should('not.exist');
  });

  it('shows the empty state when no logs match the filters', () => {
    cy.intercept('GET', SYSTEM_LOGS_API, buildLogPage(1, [], false)).as('emptyLogs');
    cy.visit('/dashboard');
    openLogManager();
    cy.wait('@emptyLogs');
    cy.get(testId('log-empty')).should('be.visible').and('contain.text', 'No system logs were returned');
    cy.get(testId('log-row')).should('not.exist');
  });

  it('surfaces an error when the log request fails', () => {
    cy.intercept('GET', SYSTEM_LOGS_API, { statusCode: 500, body: { message: 'Log service unavailable.' } }).as('failedLogs');
    cy.visit('/dashboard');
    openLogManager();
    cy.wait('@failedLogs');
    cy.get(testId('log-manager-error')).should('be.visible');
    cy.get(testId('log-row')).should('not.exist');
  });
});

export {};
