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

const loginRequestAlias = (alias = "loginRequest"): `@${string}` => (
    alias.startsWith("@") ? alias : `@${alias}`
) as `@${string}`;

const visitLoginWithCleanAuthState = () => {
    cy.clearCookies({ log: false });
    cy.clearLocalStorage();
    cy.visit("/login", {
        onBeforeLoad(win) {
            win.localStorage.clear();
            win.sessionStorage.clear();
        },
    });
};

const waitForLoginForm = (reloaded = false, attempts = 0): Cypress.Chainable<void> => {
    return cy.document({ log: false }).then((doc) => {
        if (doc.querySelector('[data-testid="login-user"]')) {
            cy.get('[data-testid="login-page"]', { timeout: 60000 }).should('be.visible');
            cy.get('[data-testid="login-user"]', { timeout: 60000 }).should('be.visible');
            cy.get('[data-testid="login-pass"]', { timeout: 60000 }).should('be.visible');
            return cy.wrap<void>(undefined, { log: false });
        }

        if (attempts < 20) {
            return cy.wait(500, { log: false }).then(() => waitForLoginForm(reloaded, attempts + 1));
        }

        if (!reloaded) {
            cy.reload();
            return waitForLoginForm(true);
        }

        throw new Error("Login form did not render after visiting /login");
    });
};

Cypress.Commands.add("visitLoginWithCleanAuthState", () => {
    visitLoginWithCleanAuthState();
    return cy.wrap<void>(undefined, { log: false });
});

Cypress.Commands.add("waitForLoginRequest", (alias = "loginRequest") => {
    return cy.wait(loginRequestAlias(alias), { timeout: 60000 })
        .its("response.statusCode")
        .should("be.oneOf", [200, 201])
        .then(() => cy.wrap<void>(undefined, { log: false }));
});

Cypress.Commands.add("docsScreenshot", (name: string, options: Partial<Cypress.ScreenshotOptions> = {}) => {
    return cy.env<{ takeScreenshots?: boolean | string }>(["takeScreenshots"]).then(({ takeScreenshots }) => {
        if (takeScreenshots !== true && takeScreenshots !== "true") {
            return cy.wrap<void>(undefined, { log: false });
        }

        const safeName = String(name || "screenshot").replace(/\\/g, "/").replace(/^\/+/, "") || "screenshot";
        const taskScreenshotName = safeName.startsWith("user-manual/") ? safeName.slice("user-manual/".length) : safeName;
        void options;
        let restoreCaptureState: (() => void) | undefined;
        let screenshotClip: { x: number; y: number; width: number; height: number; scale: number } | undefined;
        const hiddenScrollbarCss = `
            html, body { scrollbar-width: none !important; }
            html::-webkit-scrollbar, body::-webkit-scrollbar, *::-webkit-scrollbar {
                width: 0 !important;
                height: 0 !important;
                display: none !important;
            }
        `;

        return cy.window({ log: false }).then((win) => {
            const restoreFns: Array<() => void> = [];
            const appStyle = win.document.createElement("style");
            appStyle.textContent = hiddenScrollbarCss;
            (win.document.head || win.document.documentElement).appendChild(appStyle);
            restoreFns.push(() => appStyle.remove());

            try {
                const topWindow = win.top || win;
                const topDocument = topWindow.document;
                const iframe = Array.from(topDocument.querySelectorAll("iframe"))
                    .find(frame => frame.contentWindow === win)
                    || topDocument.querySelector<HTMLIFrameElement>("iframe.aut-iframe, iframe[data-cy='aut-iframe'], iframe");

                const topStyle = topDocument.createElement("style");
                topStyle.textContent = hiddenScrollbarCss;
                (topDocument.head || topDocument.documentElement).appendChild(topStyle);
                restoreFns.push(() => topStyle.remove());

                if (iframe) {
                    const rect = iframe.getBoundingClientRect();
                    const viewportWidth = Number(Cypress.config("viewportWidth")) || Math.round(win.innerWidth);
                    const viewportHeight = Number(Cypress.config("viewportHeight")) || Math.round(win.innerHeight);
                    const scale = Math.max(
                        viewportWidth / Math.max(1, rect.width),
                        viewportHeight / Math.max(1, rect.height),
                    );
                    screenshotClip = {
                        x: Math.max(0, rect.left),
                        y: Math.max(0, rect.top),
                        width: Math.max(1, rect.width),
                        height: Math.max(1, rect.height),
                        scale,
                    };
                }
            }
            catch {
                screenshotClip = undefined;
            }

            restoreCaptureState = () => {
                restoreFns.reverse().forEach(restore => restore());
                restoreCaptureState = undefined;
            };
        }).then(() => cy.wait(50, { log: false })).then(() => (
            (Cypress as any).automation("remote:debugger:protocol", {
                command: "Page.captureScreenshot",
                params: {
                    captureBeyondViewport: false,
                    ...(screenshotClip ? { clip: screenshotClip } : {}),
                    format: "png",
                    fromSurface: true,
                },
            })
        )).then((result: any) => {
            const data = typeof result === "string" ? result : result?.data;
            expect(data, `docs screenshot ${name}`).to.be.a("string").and.not.be.empty;
            return cy.task("writeDocScreenshot", {
                data,
                name: taskScreenshotName,
                specName: Cypress.spec.name,
            }, { log: false });
        }).then(() => {
            restoreCaptureState?.();
            return cy.wrap<void>(undefined, { log: false });
        });
    });
});

Cypress.Commands.add("loginAsAdmin", () => {
    cy.env(["ADMIN_USERNAME", "ADMIN_PASSWORD"]).then(({ ADMIN_USERNAME, ADMIN_PASSWORD }) => {
        if (!ADMIN_USERNAME || !ADMIN_PASSWORD) {
            throw new Error("Missing admin credentials: set DEFAULT_ADMIN_USERNAME/DEFAULT_ADMIN_PASSWORD in the root .env or ORION_ADMIN_USERNAME/ORION_ADMIN_PASSWORD in the environment");
        }
        cy.intercept({ method: "POST", pathname: "**/api/auth/login" }).as("loginRequest");
        cy.visitLoginWithCleanAuthState();
        waitForLoginForm();
        cy.get('[data-testid="login-user"]').clear().type(ADMIN_USERNAME);
        cy.get('[data-testid="login-pass"]').clear().type(ADMIN_PASSWORD, { log: false });
        cy.get('[data-testid="login-button"]').first().click();
        cy.waitForLoginRequest();
        cy.get('[data-testid="profile-menu"], [data-testid="dashboard-main"], [data-testid="dashboard-container"]')
            .filter(':visible')
            .should('have.length.greaterThan', 0);
    });
});

Cypress.Commands.add("logout", () => {
    cy.location('pathname').then((pathname) => {
        if (pathname.includes('/login')) return;
        cy.document({ log: false }).then((doc) => {
            if (!doc?.body) {
                return;
            }
            const $body = Cypress.$(doc.body);
            const profileMenu = $body.find('[data-testid="profile-menu"]:visible').first();
            if (!profileMenu.length) {
                return;
            }
            cy.scrollTo("top", { ensureScrollable: false });
            cy.wrap(profileMenu).scrollIntoView().click({ force: true });
            cy.get('[data-testid="signout-btn"]').first().scrollIntoView().click({ force: true });
            cy.get('[data-testid="login-user"]').should('exist');
            cy.clearCookies({ log: false });
            cy.clearLocalStorage();
            cy.window({ log: false }).then((win) => {
                win.localStorage.clear();
                win.sessionStorage.clear();
            });
        });
    });
});
