#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const baseDir = path.resolve(__dirname, "ui");
const guides = ["guida-docs", "guida-docs-en"];

function processFile(filePath, prefix) {
    if (path.extname(filePath) !== ".html") return;

    let content = fs.readFileSync(filePath, "utf8");
    const original = content;

    // Sostituisce path assoluti che iniziano con /guida-docs o /guida-docs-en
    // con il path relativo corretto rispetto alla root dell'estensione caricata via API
    // Il path visto dal browser è /api/extensions/guida/ui/index.html
    // I docs sono in /api/extensions/guida/ui/guida-docs/...

    // Invece di path relativi complessi, usiamo path assoluti corretti per PlanarAlly:
    // /api/extensions/guida/ui/guida-docs/...

    const re = new RegExp(`/(guida-docs(-en)?)/`, "g");
    content = content.replace(re, `/api/extensions/guida/ui/$1/`);

    if (content !== original) {
        fs.writeFileSync(filePath, content);
        console.log(`Fixed paths in: ${filePath}`);
    }
}

function walk(dir, prefix) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            walk(fullPath, prefix);
        } else {
            processFile(fullPath, prefix);
        }
    }
}

guides.forEach(guide => {
    const guidePath = path.join(baseDir, guide);
    if (fs.existsSync(guidePath)) {
        console.log(`Processing guide: ${guide}`);
        walk(guidePath, guide);
    }
});
