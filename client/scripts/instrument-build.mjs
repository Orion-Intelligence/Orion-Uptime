#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createInstrumenter } from "istanbul-lib-instrument";

const clientDir = fileURLToPath(new URL("..", import.meta.url));
const buildDir = path.resolve(clientDir, process.argv[2] || "build");
const applicationSource = /^src\//;

if (!fs.existsSync(path.join(buildDir, "index.html"))) {
    console.error(`No Angular build found in ${buildDir}; run "ng build --configuration instrumented" first.`);
    process.exit(1);
}

const instrumenter = createInstrumenter({
    coverageVariable: "__coverage__",
    coverageGlobalScope: "window",
    coverageGlobalScopeFunc: false,
    esModules: true,
    compact: true,
    preserveComments: false,
    produceSourceMap: true,
    autoWrap: false,
});

const resolveSources = (sourceMap) => ({
    ...sourceMap,
    sources: sourceMap.sources.map((source) => (path.isAbsolute(source) ? source : path.resolve(clientDir, source))),
});

const chunks = fs
    .readdirSync(buildDir)
    .filter((name) => name.endsWith(".js") && fs.existsSync(path.join(buildDir, `${name}.map`)))
    .sort();

let instrumentedCount = 0;
for (const name of chunks) {
    const jsPath = path.join(buildDir, name);
    const mapPath = `${jsPath}.map`;
    const sourceMap = JSON.parse(fs.readFileSync(mapPath, "utf8"));
    const sources = Array.isArray(sourceMap.sources) ? sourceMap.sources : [];
    if (!sources.some((source) => applicationSource.test(source))) {
        console.log(`skip      ${name} (no application sources)`);
        continue;
    }

    const code = fs.readFileSync(jsPath, "utf8").replace(/\n?\/\/# sourceMappingURL=.*$/, "");
    const startedAt = Date.now();
    const instrumented = instrumenter.instrumentSync(code, jsPath, resolveSources(sourceMap));
    const outputMap = instrumenter.lastSourceMap();

    fs.writeFileSync(jsPath, `${instrumented}\n//# sourceMappingURL=${name}.map\n`);
    fs.writeFileSync(mapPath, JSON.stringify(outputMap));
    instrumentedCount += 1;
    console.log(`instrument ${name} (${(instrumented.length / 1024 / 1024).toFixed(2)} MB, ${Date.now() - startedAt} ms)`);
}

if (instrumentedCount === 0) {
    console.error("No application bundle was instrumented; make sure the build was produced with source maps enabled.");
    process.exit(1);
}

console.log(`Instrumented ${instrumentedCount} bundle(s) in ${path.relative(clientDir, buildDir) || "."}`);
