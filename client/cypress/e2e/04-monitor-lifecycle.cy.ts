const testId = (id: string) => `[data-testid="${id}"]`;

interface MonitorScenario {
  label: string;
  listPath: string;
  listTitle: string;
  newTitle: string;
  editTitle: string;
  configType?: string;
  fixture?: string;
  listApi: string;
  createApi: string;
  updateApi: string;
  deleteApi: string;
  deleteUrl: (id: string) => string;
  fillCreate: (name: string) => void;
  applyEdits: (name: string) => void;
  assertImportedForm?: () => void;
  assertEditedForm: (name: string) => void;
}

const E2E_NAME_PREFIX = 'E2E ';

const uniqueName = (label: string) => (
  `E2E ${label} lifecycle ${Date.now()} ${Math.floor(Math.random() * 1_000_000)}`
);

const slugFor = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');

const detailLinkFor = (scenario: MonitorScenario, id: string) => (
  `${testId('monitor-detail-link')}[href="${scenario.listPath}/${id}"]`
);

const cardById = (scenario: MonitorScenario, id: string) => (
  cy.get(detailLinkFor(scenario, id)).closest(testId('monitor-card'))
);

const monitorIdByName = (name: string): Cypress.Chainable<string> => (
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

const openList = (scenario: MonitorScenario) => {
  cy.visit(scenario.listPath);
  cy.get(testId('resource-list-page')).should('be.visible');
  cy.get(testId('page-title')).should('contain.text', scenario.listTitle);
  disableNoticeOverlay();
};

const assertNameRequired = (scenario: MonitorScenario) => {
  const attempts = { count: 0 };
  cy.intercept('POST', scenario.createApi, () => { attempts.count += 1; });
  cy.get(testId('monitor-name')).clear();
  cy.get(testId('save-button')).click();
  cy.get(testId('resource-editor-error')).should('be.visible').and('contain.text', 'Name is required');
  cy.location('pathname').should('eq', `${scenario.listPath}/new`);
  cy.then(() => {
    expect(attempts.count, `${scenario.label} create requests while name is empty`).to.eq(0);
  });
};

const createMonitor = (scenario: MonitorScenario, name: string): Cypress.Chainable<string> => {
  cy.get(testId('new-monitor-button')).click();
  cy.location('pathname').should('eq', `${scenario.listPath}/new`);
  cy.get(testId('page-title')).should('contain.text', scenario.newTitle);
  cy.get(testId('resource-editor-form')).should('be.visible');

  assertNameRequired(scenario);

  cy.get(testId('monitor-name')).clear().type(name);
  scenario.fillCreate(name);

  cy.intercept('POST', scenario.createApi).as('createMonitor');
  cy.get(testId('save-button')).click();
  cy.wait('@createMonitor').then(({ request, response }) => {
    expect(response?.statusCode, `${scenario.label} create status`).to.be.oneOf([200, 201]);
    expect(request.body.name, `${scenario.label} name sent`).to.eq(name);
  });

  cy.location('pathname').should('eq', scenario.listPath);

  return monitorIdByName(name).then((id) => {
    cardById(scenario, id).should('be.visible');
    return cy.wrap(id);
  });
};

const pauseMonitor = (scenario: MonitorScenario, id: string) => {
  cy.intercept('PUT', scenario.updateApi).as('pauseMonitor');
  cardById(scenario, id).find(testId('monitor-toggle-active-button')).should('contain.text', 'Pause').click();
  cy.wait('@pauseMonitor').then(({ request, response }) => {
    expect(response?.statusCode, `${scenario.label} pause status`).to.eq(200);
    expect(request.body.is_active, `${scenario.label} is_active on pause`).to.eq(false);
  });
  cardById(scenario, id).find(testId('monitor-card-status')).should('have.text', 'paused');
  cardById(scenario, id).find(testId('monitor-toggle-active-button')).should('contain.text', 'Start');
};

const startMonitor = (scenario: MonitorScenario, id: string) => {
  cy.intercept('PUT', scenario.updateApi).as('startMonitor');
  cardById(scenario, id).find(testId('monitor-toggle-active-button')).should('contain.text', 'Start').click();
  cy.wait('@startMonitor').then(({ request, response }) => {
    expect(response?.statusCode, `${scenario.label} start status`).to.eq(200);
    expect(request.body.is_active, `${scenario.label} is_active on start`).to.eq(true);
  });
  cardById(scenario, id).find(testId('monitor-card-status')).should('not.have.text', 'paused');
  cardById(scenario, id).find(testId('monitor-toggle-active-button')).should('contain.text', 'Pause');
};

const editMonitor = (scenario: MonitorScenario, id: string, name: string, editedName: string) => {
  cardById(scenario, id).find(testId('monitor-edit-link')).click();
  cy.location('pathname').should('eq', `${scenario.listPath}/${id}/edit`);
  cy.get(testId('page-title')).should('contain.text', scenario.editTitle);
  cy.get(testId('monitor-name')).should('have.value', name);

  cy.get(testId('monitor-name')).clear().type(editedName);
  scenario.applyEdits(editedName);

  cy.intercept('PUT', scenario.updateApi).as('updateMonitor');
  cy.get(testId('save-button')).click();
  cy.wait('@updateMonitor').then(({ request, response }) => {
    expect(response?.statusCode, `${scenario.label} update status`).to.eq(200);
    expect(request.body.name, `${scenario.label} edited name sent`).to.eq(editedName);
  });

  cy.location('pathname').should('eq', scenario.listPath);
  cardById(scenario, id).find(testId('monitor-name')).should('have.text', editedName);

  cardById(scenario, id).find(testId('monitor-edit-link')).click();
  cy.get(testId('monitor-name')).should('have.value', editedName);
  scenario.assertEditedForm(editedName);
  cy.get(testId('cancel-button')).click();
  cy.location('pathname').should('eq', scenario.listPath);
};

const exportMonitor = (scenario: MonitorScenario, id: string) => {
  const configType = scenario.configType;
  if (!configType) {
    return;
  }
  cy.intercept('GET', `**/api/monitor-configs/${configType}/${id}`).as('exportMonitor');
  cardById(scenario, id).find(testId('monitor-export-button')).click();
  cy.wait('@exportMonitor').then(({ response }) => {
    expect(response?.statusCode, `${scenario.label} export status`).to.eq(200);
    expect(response?.body?.data?.monitor_id, `${scenario.label} exported ID`).to.eq(id);
    expect(response?.body?.data?.monitor_type, `${scenario.label} exported type`).to.eq(configType);
  });
  cardById(scenario, id).find(testId('monitor-export-button')).should('contain.text', 'Export');
};

const cancelDelete = (scenario: MonitorScenario, id: string, name: string) => {
  cardById(scenario, id).find(testId('monitor-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-cancel')).click();
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  cardById(scenario, id).find(testId('monitor-name')).should('have.text', name);
};

const confirmDelete = (scenario: MonitorScenario, id: string, name: string) => {
  cy.intercept('DELETE', scenario.deleteApi).as('deleteMonitor');
  cardById(scenario, id).find(testId('monitor-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', name);
  cy.get(testId('delete-confirmation-confirm')).click();
  cy.wait('@deleteMonitor').its('response.statusCode').should('eq', 200);
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  cy.get(detailLinkFor(scenario, id)).should('not.exist');
};

const importMonitor = (scenario: MonitorScenario): Cypress.Chainable<string> => {
  const fixture = String(scenario.fixture);
  cy.intercept('POST', '**/api/monitor-configs/import*').as('importMonitor');
  cy.get(testId('monitor-config-import-input')).selectFile(fixture, { force: true });

  return cy.wait('@importMonitor').then(({ response }) => {
    expect(response?.statusCode, `${scenario.label} import status`).to.be.oneOf([200, 201]);
    expect(response?.body?.data?.monitor_type, `${scenario.label} imported type`).to.eq(scenario.configType);

    const id = String(response?.body?.data?.monitor_id ?? '');
    expect(id, `${scenario.label} imported monitor ID`).to.not.equal('');
    cardById(scenario, id).should('be.visible');
      return cy.wrap(id);
  });
};

const runMonitorLifecycle = (scenario: MonitorScenario) => {
  const name = uniqueName(scenario.label);
  const editedName = `${name} edited`;

  openList(scenario);

  createMonitor(scenario, name).then((monitorId) => {
    pauseMonitor(scenario, monitorId);
    startMonitor(scenario, monitorId);
    editMonitor(scenario, monitorId, name, editedName);
    exportMonitor(scenario, monitorId);
    cancelDelete(scenario, monitorId, editedName);
    confirmDelete(scenario, monitorId, editedName);
  });

  if (!scenario.fixture) {
    return;
  }

  importMonitor(scenario).then((importedId) => {
    cardById(scenario, importedId).find(testId('monitor-name')).invoke('text').then((importedName) => {
      const assertImportedForm = scenario.assertImportedForm;
      if (assertImportedForm) {
        cardById(scenario, importedId).find(testId('monitor-edit-link')).click();
        cy.location('pathname').should('eq', `${scenario.listPath}/${importedId}/edit`);
        assertImportedForm();
        cy.get(testId('cancel-button')).click();
        cy.location('pathname').should('eq', scenario.listPath);
      }
      confirmDelete(scenario, importedId, importedName);
    });
  });
};

const timingFields = (interval: string, timeout: string, responseTime: string) => {
  cy.get(testId('check-interval')).clear().type(interval);
  cy.get(testId('timeout')).clear().type(timeout);
  cy.get(testId('expected-response-time')).clear().type(responseTime);
};

const assertTimingFields = (interval: string, timeout: string, responseTime: string) => {
  cy.get(testId('check-interval')).should('have.value', interval);
  cy.get(testId('timeout')).should('have.value', timeout);
  cy.get(testId('expected-response-time')).should('have.value', responseTime);
};

const scenarios: MonitorScenario[] = [
  {
    label: 'HTTP',
    listPath: '/monitors/http',
    listTitle: 'HTTP monitors',
    newTitle: 'New HTTP monitor',
    editTitle: 'Edit HTTP monitor',
    configType: 'HTTP',
    fixture: 'src/assets/cypress data/04-http-monitor-import.json',
    listApi: '/api/HTTP_monitors/list_all',
    createApi: '**/api/HTTP_monitors/create',
    updateApi: '**/api/HTTP_monitors/*/update',
    deleteApi: '**/api/HTTP_monitors/*/delete',
    deleteUrl: id => `/api/HTTP_monitors/${id}/delete`,
    fillCreate: (name) => {
      cy.get(testId('monitor-url')).clear().type(`https://example.com/e2e-${slugFor(name)}`);
      cy.get(testId('monitor-expected-status')).clear().type('200');
      timingFields('60', '10', '1000');
    },
    applyEdits: (name) => {
      cy.get(testId('monitor-url')).clear().type(`https://example.com/e2e-${slugFor(name)}`);
      cy.get(testId('monitor-expected-status')).clear().type('204');
      timingFields('120', '15', '1500');
    },
    assertImportedForm: () => {
      cy.get(testId('monitor-name')).should('have.value', 'E2E HTTP import fixture');
      cy.get(testId('monitor-url')).should('have.value', 'https://example.com/e2e-http-import-fixture-04');
      cy.get(testId('monitor-expected-status')).should('have.value', '200');
      assertTimingFields('60', '10', '');
    },
    assertEditedForm: (name) => {
      cy.get(testId('monitor-url')).should('have.value', `https://example.com/e2e-${slugFor(name)}`);
      cy.get(testId('monitor-expected-status')).should('have.value', '204');
      assertTimingFields('120', '15', '1500');
    },
  },
  {
    label: 'API',
    listPath: '/monitors/api',
    listTitle: 'API monitors',
    newTitle: 'New API monitor',
    editTitle: 'Edit API monitor',
    configType: 'API',
    fixture: 'src/assets/cypress data/04-api-monitor-import.json',
    listApi: '/api/API_monitors/list_all',
    createApi: '**/api/API_monitors/create',
    updateApi: '**/api/API_monitors/*',
    deleteApi: '**/api/API_monitors/*',
    deleteUrl: id => `/api/API_monitors/${id}`,
    fillCreate: (name) => {
      cy.get(testId('monitor-url')).clear().type(`https://example.com/e2e-${slugFor(name)}`);
      cy.get(testId('api-method')).select('GET');
      cy.get(testId('monitor-expected-status')).clear().type('200');
      timingFields('60', '10', '1000');
    },
    applyEdits: (name) => {
      cy.get(testId('monitor-url')).clear().type(`https://example.com/e2e-${slugFor(name)}`);
      cy.get(testId('api-method')).select('POST');
      cy.get(testId('monitor-expected-status')).clear().type('201');
      cy.get(testId('api-expected-content-type')).clear().type('application/json');
      timingFields('120', '15', '1500');
    },
    assertImportedForm: () => {
      cy.get(testId('monitor-name')).should('have.value', 'E2E API import fixture');
      cy.get(testId('monitor-url')).should('have.value', 'https://example.com/e2e-api-import-fixture-04');
      cy.get(testId('api-method')).should('have.value', 'GET');
      cy.get(testId('monitor-expected-status')).should('have.value', '200');
      assertTimingFields('60', '10', '');
    },
    assertEditedForm: (name) => {
      cy.get(testId('monitor-url')).should('have.value', `https://example.com/e2e-${slugFor(name)}`);
      cy.get(testId('api-method')).should('have.value', 'POST');
      cy.get(testId('monitor-expected-status')).should('have.value', '201');
      cy.get(testId('api-expected-content-type')).should('have.value', 'application/json');
      assertTimingFields('120', '15', '1500');
    },
  },
  {
    label: 'Ping',
    listPath: '/monitors/ping',
    listTitle: 'Ping monitors',
    newTitle: 'New Ping monitor',
    editTitle: 'Edit Ping monitor',
    configType: 'ping',
    fixture: 'src/assets/cypress data/04-ping-monitor-import.json',
    listApi: '/api/ping-monitors/list_all',
    createApi: '**/api/ping-monitors/create',
    updateApi: '**/api/ping-monitors/*/update',
    deleteApi: '**/api/ping-monitors/*/delete',
    deleteUrl: id => `/api/ping-monitors/${id}/delete`,
    fillCreate: () => {
      cy.get(testId('monitor-host')).clear().type('example.com');
      timingFields('60', '10', '1000');
    },
    applyEdits: () => {
      cy.get(testId('monitor-host')).clear().type('example.org');
      timingFields('120', '15', '1500');
    },
    assertImportedForm: () => {
      cy.get(testId('monitor-name')).should('have.value', 'E2E ping import fixture');
      cy.get(testId('monitor-host')).should('have.value', 'example.com');
      assertTimingFields('60', '10', '');
    },
    assertEditedForm: () => {
      cy.get(testId('monitor-host')).should('have.value', 'example.org');
      assertTimingFields('120', '15', '1500');
    },
  },
  {
    label: 'Heartbeat',
    listPath: '/monitors/heartbeat',
    listTitle: 'Heartbeat monitors',
    newTitle: 'New Heartbeat monitor',
    editTitle: 'Edit Heartbeat monitor',
    configType: 'heartbeat',
    fixture: 'src/assets/cypress data/04-heartbeat-monitor-import.json',
    listApi: '/api/heartbeat-monitors/list_all',
    createApi: '**/api/heartbeat-monitors/create',
    updateApi: '**/api/heartbeat-monitors/*/update',
    deleteApi: '**/api/heartbeat-monitors/*/delete',
    deleteUrl: id => `/api/heartbeat-monitors/${id}/delete`,
    fillCreate: () => {
      cy.get(testId('heartbeat-interval')).clear().type('300');
      cy.get(testId('heartbeat-grace')).clear().type('60');
    },
    applyEdits: () => {
      cy.get(testId('heartbeat-interval')).clear().type('600');
      cy.get(testId('heartbeat-grace')).clear().type('120');
    },
    assertImportedForm: () => {
      cy.get(testId('monitor-name')).should('have.value', 'E2E heartbeat import fixture');
      cy.get(testId('heartbeat-interval')).should('have.value', '300');
      cy.get(testId('heartbeat-grace')).should('have.value', '60');
    },
    assertEditedForm: () => {
      cy.get(testId('heartbeat-interval')).should('have.value', '600');
      cy.get(testId('heartbeat-grace')).should('have.value', '120');
    },
  },
];

describe('Monitor lifecycle', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    scenarios.forEach((scenario) => {
      cy.request({ url: scenario.listApi, failOnStatusCode: false }).then((response) => {
        const rows = (response.body?.data ?? []) as Array<{ id: string; name: string }>;
        rows
          .filter(row => String(row.name).startsWith(E2E_NAME_PREFIX))
          .forEach((row) => {
            cy.request({ method: 'DELETE', url: scenario.deleteUrl(row.id), failOnStatusCode: false });
          });
      });
    });
  });

  scenarios.forEach((scenario) => {
    it(`manages a ${scenario.label} monitor end to end`, () => {
      runMonitorLifecycle(scenario);
    });
  });
});

export {};
