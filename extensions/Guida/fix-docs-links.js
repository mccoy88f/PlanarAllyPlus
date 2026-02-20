#!/usr/bin/env node
/**
 * Corregge i link e le immagini nella documentazione che usano path assoluti
 * (/docs/, /logos/, /blog/, ecc.) aggiungendo il prefix base (guida-docs o guida-docs-en).
 *
 * Uso: node fix-docs-links.js [docs_dir] [prefix]
 *   docs_dir: path a docs/ o docs-en/ (default: docs)
 *   prefix:   guida-docs o guida-docs-en (default: guida-docs)
 */
const fs = require("fs");
const path = require("path");

const docsDir = path.resolve(process.cwd(), process.argv[2] || "docs");
const prefix = process.argv[3] || "guida-docs";

function fixHtml(html, basePrefix) {
  // Sostituisce href="/..." e src="/..." (esclusi // esterni e già prefissati)
  const re = new RegExp(
    `(href|src)=("\\/)(?!${basePrefix}\\/|\\/)`,
    "g"
  );
  return html.replace(re, `$1=$2${basePrefix}/`);
}

function processFile(filePath) {
  const ext = path.extname(filePath);
  if (ext !== ".html") return;

  let content = fs.readFileSync(filePath, "utf8");
  const fixed = fixHtml(content, prefix);
  if (content !== fixed) {
    fs.writeFileSync(filePath, fixed);
    console.log("Fixed:", path.relative(docsDir, filePath));
  }
}

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      walk(full);
    } else if (e.isFile()) {
      processFile(full);
    }
  }
}

if (!fs.existsSync(docsDir)) {
  console.error("Directory non trovata:", docsDir);
  process.exit(1);
}
console.log("Elaborazione", docsDir, "con prefix", prefix);
walk(docsDir);
console.log("Fatto.");
