import { defineConfig } from "cypress";
import fs from "node:fs";
import path from "node:path";

const projectDir = typeof __dirname !== "undefined" ? __dirname : process.cwd();

const readRootEnv = (): Record<string, string> => {
    const envPath = path.resolve(projectDir, "..", ".env");
    if (!fs.existsSync(envPath)) {
        return {};
    }
    const values: Record<string, string> = {};
    for (const rawLine of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line || line.startsWith("#")) {
            continue;
        }
        const separator = line.indexOf("=");
        if (separator === -1) {
            continue;
        }
        const key = line.slice(0, separator).trim();
        let value = line.slice(separator + 1).trim();
        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
        }
        values[key] = value;
    }
    return values;
};

const rootEnv = readRootEnv();
const adminUsername = process.env["ORION_ADMIN_USERNAME"] || rootEnv["DEFAULT_ADMIN_USERNAME"] || "admin";
const adminPassword = process.env["ORION_ADMIN_PASSWORD"] || rootEnv["DEFAULT_ADMIN_PASSWORD"] || "";

export default defineConfig({
    allowCypressEnv: false,
    video: false,
    screenshotsFolder: "cypress/error",
    screenshotOnRunFailure: true,
    numTestsKeptInMemory: 0,
    watchForFileChanges: false,
    trashAssetsBeforeRuns: false,
    experimentalMemoryManagement: true,
    experimentalFastVisibility: true,
    retries: 0,
    env: {
        language: "en",
        ADMIN_USERNAME: adminUsername,
        ADMIN_PASSWORD: adminPassword,
        takeScreenshots: false,
    },
    e2e: {
        specPattern: "cypress/e2e/**/*.{cy,spec}.{ts,js}",
        supportFile: "cypress/support/e2e.ts",
        testIsolation: true,
        setupNodeEvents(on, config) {
            const takeScreenshots = config.env["takeScreenshots"];
            if (takeScreenshots === true || takeScreenshots === "true") {
                config.screenshotsFolder = "../docs/screenshots";
            }
            on("after:screenshot", (details) => {
                if (!details.testFailure) {
                    return;
                }
                const screenshotsFolder =
                    typeof config.screenshotsFolder === "string" ? config.screenshotsFolder : "cypress/error";
                const screenshotRoot = path.resolve(config.projectRoot, screenshotsFolder);
                const relativePath = path.relative(screenshotRoot, details.path);
                const targetPath = path.resolve(config.projectRoot, "cypress", "error", relativePath);

                if (details.path === targetPath) {
                    return;
                }

                fs.mkdirSync(path.dirname(targetPath), { recursive: true });
                fs.renameSync(details.path, targetPath);

                return { path: targetPath };
            });
            on("before:browser:launch", (browser, launchOptions) => {
                if (browser.family === "chromium") {
                    launchOptions.args.push("--start-maximized");
                    launchOptions.args.push("--window-size=1920,1080");
                    launchOptions.args.push("--force-device-scale-factor=1");
                }
                return launchOptions;
            });
            on("task", {
                log(_) {
                    return null;
                },
                table(_) {
                    return null;
                },
                writeDocScreenshot({ data, name, specName }) {
                    const screenshotsFolder =
                        typeof config.screenshotsFolder === "string" ? config.screenshotsFolder : "cypress/error";
                    const screenshotRoot = path.resolve(config.projectRoot, screenshotsFolder);
                    const safeSpecName = String(specName || "unknown-spec").replace(/[\\/]/g, "_");
                    const safeName = String(name || "screenshot").replace(/\\/g, "/").replace(/^\/+/, "");
                    const targetPath = path.resolve(screenshotRoot, safeSpecName, "user-manual", `${safeName}.png`);

                    if (!targetPath.startsWith(`${screenshotRoot}${path.sep}`)) {
                        throw new Error(`Refusing to write docs screenshot outside screenshots folder: ${targetPath}`);
                    }

                    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
                    fs.writeFileSync(targetPath, Buffer.from(String(data), "base64"));
                    return null;
                },
            });
            return config;
        },
        baseUrl: process.env["ORION_E2E_BASE_URL"] || "http://127.0.0.1:4400",
        viewportWidth: 1920,
        viewportHeight: 1080,
        defaultCommandTimeout: 60000,
        requestTimeout: 60000,
        responseTimeout: 60000,
        pageLoadTimeout: 60000,
        execTimeout: 60000,
        taskTimeout: 60000,
        waitForAnimations: true,
        animationDistanceThreshold: 5,
    },
});
