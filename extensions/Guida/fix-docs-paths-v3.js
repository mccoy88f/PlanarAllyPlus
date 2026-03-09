#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const baseDir = path.resolve(__dirname, "ui");
const guides = ["guida-docs", "guida-docs-en"];

function processFile(filePath) {
    if (path.extname(filePath) !== ".html") return;

    let content = fs.readFileSync(filePath, "utf8");
    const original = content;

    const guideName = filePath.includes("guida-docs-en") ? "guida-docs-en" : "guida-docs";
    const guideRootDir = path.join(baseDir, guideName);
    const depth = path.relative(guideRootDir, path.dirname(filePath)).split(path.sep).filter(p => p && p !== ".").length;

    // Prefix relativo per arrivare alla root della guida
    const relativeToRoot = depth > 0 ? "../".repeat(depth) : "./";

    // Strategia: Trasformiamo QUALSIASI path che inizia con /api/extensions/guida/ui/ o /guida-docs/
    // in un path relativo basato sulla profondità del file corrente.

    // 1. Pulizia path assoluti API
    content = content.split(`"/api/extensions/guida/ui/guida-docs/`).join(`"${relativeToRoot}`);
    content = content.split(`"/api/extensions/guida/ui/guida-docs-en/`).join(`"${relativeToRoot}`);
    content = content.split(`'/api/extensions/guida/ui/guida-docs/`).join(`'${relativeToRoot}`);
    content = content.split(`'/api/extensions/guida/ui/guida-docs-en/`).join(`'${relativeToRoot}`);

    // 2. Pulizia path assoluti root (caso in cui non siano stati ancora trasformati)
    content = content.split(`"/guida-docs/`).join(`"${relativeToRoot}`);
    content = content.split(`"/guida-docs-en/`).join(`"${relativeToRoot}`);
    content = content.split(`'/guida-docs/`).join(`'${relativeToRoot}`);
    content = content.split(`'/guida-docs-en/`).join(`'${relativeToRoot}`);

    if (content !== original) {
        fs.writeFileSync(filePath, content);
        console.log(`Fixed paths in: ${filePath} (depth: ${depth}, prefix: ${relativeToRoot})`);
    }
}

function walk(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            walk(fullPath);
        } else {
            processFile(fullPath);
        }
    }
}

guides.forEach(guide => {
    const guidePath = path.join(baseDir, guide);
    if (fs.existsSync(guidePath)) {
        console.log(`Processing guide: ${guide}`);
        walk(guidePath);
    }
});
