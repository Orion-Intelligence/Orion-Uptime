const testId = (id: string) => `[data-testid="${id}"]`;

const USERS_PATH = '/users';
const E2E_USERNAME_PREFIX = 'e2e-user-';

const uniqueUsername = () => `${E2E_USERNAME_PREFIX}${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;

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

const cardByUsername = (username: string) => (
  cy.contains(testId('user-name'), username).closest(testId('user-card'))
);

const openUserList = () => {
  cy.visit(USERS_PATH);
  cy.get(testId('user-list-page')).should('be.visible');
  cy.get(testId('new-user-button')).should('be.visible');
  disableNoticeOverlay();
};

const assertRegistrationValidation = () => {
  const attempts = { count: 0 };
  cy.intercept('POST', '**/api/users/create', () => { attempts.count += 1; });
  cy.get(testId('register-submit')).click();
  cy.scrollTo('top', { ensureScrollable: false });
  cy.get(testId('register-user-error')).should('be.visible').and('contain.text', 'Username must be 3');
  cy.location('pathname').should('eq', `${USERS_PATH}/new`);
  cy.then(() => {
    expect(attempts.count, 'create requests while the form is invalid').to.eq(0);
  });
};

const registerUser = (username: string, password: string) => {
  cy.get(testId('new-user-button')).click();
  cy.location('pathname').should('eq', `${USERS_PATH}/new`);
  cy.get(testId('register-user-form')).should('be.visible');

  assertRegistrationValidation();

  cy.get(testId('register-username')).clear().type(username);
  cy.get(testId('register-password')).clear().type(password, { log: false });

  cy.intercept('POST', '**/api/users/create').as('createUser');
  cy.get(testId('register-submit')).click();

  return cy.wait('@createUser').then(({ request, response }) => {
    expect(response?.statusCode, 'create user status').to.be.oneOf([200, 201]);
    expect(request.body.username, 'username sent').to.eq(username);

    const id = String(response?.body?.data?.id ?? '');
    expect(id, 'created user ID').to.not.equal('');
    expect(response?.body?.data?.role, 'created user role').to.eq('viewer');

    cy.location('pathname').should('eq', USERS_PATH);
    disableNoticeOverlay();
    cardByUsername(username).should('be.visible');
    cardByUsername(username).find(testId('user-status')).should('have.text', 'Active');
    return cy.wrap(id);
  });
};

const deactivateUser = (username: string) => {
  cy.intercept('PUT', '**/api/users/*/update').as('deactivateUser');
  cardByUsername(username).find(testId('user-toggle-active-button')).should('contain.text', 'Deactivate').click();
  cy.wait('@deactivateUser').then(({ request, response }) => {
    expect(response?.statusCode, 'deactivate status').to.eq(200);
    expect(request.body.is_active, 'is_active sent when deactivating').to.eq(false);
  });
  cardByUsername(username).find(testId('user-status')).should('have.text', 'Disabled');
  cardByUsername(username).find(testId('user-toggle-active-button')).should('contain.text', 'Activate');
};

const activateUser = (username: string) => {
  cy.intercept('PUT', '**/api/users/*/update').as('activateUser');
  cardByUsername(username).find(testId('user-toggle-active-button')).should('contain.text', 'Activate').click();
  cy.wait('@activateUser').then(({ request, response }) => {
    expect(response?.statusCode, 'activate status').to.eq(200);
    expect(request.body.is_active, 'is_active sent when activating').to.eq(true);
  });
  cardByUsername(username).find(testId('user-status')).should('have.text', 'Active');
  cardByUsername(username).find(testId('user-toggle-active-button')).should('contain.text', 'Deactivate');
};

const deleteUser = (username: string) => {
  cardByUsername(username).find(testId('user-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', username);
  cy.get(testId('delete-confirmation-cancel')).click();
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  cardByUsername(username).should('be.visible');

  cy.intercept('DELETE', '**/api/users/*/delete').as('deleteUser');
  cardByUsername(username).find(testId('user-delete-button')).click();
  cy.get(testId('delete-confirmation-dialog')).should('be.visible').and('contain.text', username);
  cy.get(testId('delete-confirmation-confirm')).click();
  cy.wait('@deleteUser').its('response.statusCode').should('eq', 200);
  cy.get(testId('delete-confirmation-dialog')).should('not.exist');
  cy.contains(testId('user-name'), username).should('not.exist');
};

describe('Users', () => {
  beforeEach(() => {
    cy.loginAsAdmin();
  });

  afterEach(() => {
    cy.request({ url: '/api/users/list', failOnStatusCode: false }).then((response) => {
      const rows = (response.body?.data ?? []) as Array<{ id: string; username: string }>;
      rows.filter(row => String(row.username).startsWith(E2E_USERNAME_PREFIX)).forEach((row) => {
        cy.request({ method: 'DELETE', url: `/api/users/${row.id}/delete`, failOnStatusCode: false });
      });
    });
  });

  it('registers a viewer, deactivates and reactivates it, then removes it', () => {
    const username = uniqueUsername();

    openUserList();
    registerUser(username, 'E2ePassword123!').then(() => {
      deactivateUser(username);
      activateUser(username);
      deleteUser(username);
    });
  });
});

export {};
