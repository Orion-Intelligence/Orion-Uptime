import { E2E_NAME_PREFIX, cleanupE2eHttpMonitors, createHttpMonitor, deleteHttpMonitorViaUi, uniqueSuffix } from './controllers/shared.controller';
import { assertPublicStatusPage, cleanupE2eStatusPages, createStatusPage, deleteStatusPage, editStatusPage } from './controllers/07-status-pages.controller';

describe('Status pages', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cleanupE2eStatusPages();
    cleanupE2eHttpMonitors();
  });

  it('publishes a monitor on a status page, serves it publicly, edits it, then removes everything', () => {
    const suffix = uniqueSuffix();
    const monitorName = `${E2E_NAME_PREFIX}HTTP status page ${suffix}`;
    const pageName = `${E2E_NAME_PREFIX}Status page ${suffix}`;
    const editedPageName = `${pageName} edited`;
    const pageDescription = `Public availability for ${suffix}`;

    createHttpMonitor(monitorName).then((monitorId) => {
      createStatusPage(pageName, pageDescription, monitorName, monitorId).then((page) => {
        assertPublicStatusPage(page.slug, pageName, monitorName, monitorId);
        editStatusPage(page.id, pageName, editedPageName);
        deleteStatusPage(page.id, editedPageName);
        deleteHttpMonitorViaUi(monitorId, monitorName);
      });
    });
  });
});

export {};
