export {};
declare global {
    namespace Cypress {
        interface Chainable {
            loginAsAdmin(): Chainable<void>;
            visitLoginWithCleanAuthState(): Chainable<void>;
            waitForLoginRequest(alias?: string): Chainable<void>;
            logout(): Chainable<void>;
            docsScreenshot(name: string, options?: Partial<Cypress.ScreenshotOptions>): Chainable<void>;
        }
    }
}
