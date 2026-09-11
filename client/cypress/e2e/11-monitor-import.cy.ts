import { disableNoticeOverlay, E2E_NAME_PREFIX, cleanupE2eHttpMonitors, testId, uniqueSuffix } from './controllers/shared.controller';

const HTTP_TAB = '/monitors/http';

const selectImport = (contents: string, fileName: string, mimeType = 'application/json') => {
  cy.get('input[type="file"]').selectFile({ contents: Cypress.Buffer.from(contents), fileName, mimeType }, { force: true });
};

describe('Monitor configuration import parsing', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
    cy.visit(HTTP_TAB);
    cy.get(testId('resource-list-page')).should('be.visible');
    cy.contains('button', 'Import file').should('be.visible');
    disableNoticeOverlay();
  });

  afterEach(() => {
    cleanupE2eHttpMonitors();
  });

  it('rejects an empty file', () => {
    selectImport('   \n   ', 'empty.json');
    cy.get('[role="alert"]').should('contain.text', 'The selected file is empty');
  });

  it('rejects an unsupported file extension', () => {
    selectImport('{}', 'config.yaml', 'application/x-yaml');
    cy.get('[role="alert"]').should('contain.text', 'unsupported extension');
  });

  it('rejects a JSON array that is not a configuration object', () => {
    selectImport('[1, 2, 3]', 'array.json');
    cy.get('[role="alert"]').should('contain.text', 'must contain one JSON monitor configuration object');
  });

  it('rejects content that cannot be repaired', () => {
    selectImport('this is not json {{{', 'garbage.txt', 'text/plain');
    cy.get('[role="alert"]').should('contain.text', 'could not be repaired');
  });

  it('repairs JSON5 in a fenced block and reports a mismatched monitor tab', () => {
    const fenced = [
      '```json',
      '{',
      '  // exported configuration',
      '  monitor_type: "API",',
      '  name: "Wrong tab",',
      '  url: "https://example.com/api",',
      '  expected_status_code: 200,',
      '  check_interval: 60,',
      '  timeout: 10,',
      '}',
      '```',
    ].join('\n');
    selectImport(fenced, 'api.txt', 'text/plain');
    cy.get('[role="alert"]').should('contain.text', 'cannot be imported from the HTTP monitor tab');
  });

  it('imports a repaired JSON5 HTTP configuration and reports the repair', () => {
    const name = `${E2E_NAME_PREFIX}Import ${uniqueSuffix()}`;
    const json5 = [
      '{',
      "  monitor_type: 'HTTP', // repaired: single quotes, comment, trailing comma",
      `  name: '${name}',`,
      "  url: 'https://example.com/e2e-import',",
      '  expected_status_code: 200,',
      '  check_interval: 60,',
      '  timeout: 10,',
      '}',
    ].join('\n');
    cy.intercept('POST', '**/api/monitor-configs/import*').as('importConfig');
    selectImport(json5, 'http.json');
    cy.wait('@importConfig').its('response.statusCode').should('be.oneOf', [200, 201]);
    cy.get(testId('app-notification')).should('contain.text', 'Common syntax issues were repaired.');
  });
});
