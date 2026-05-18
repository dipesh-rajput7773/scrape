const fs = require('fs');
const path = require('path');

const SKIP = new Set([
  'node_modules', 'venv', '.git', '__pycache__', '.claude',
  'package.json', 'package-lock.json', 'index.js'
]);

const TEXT_EXTS = new Set(['.py', '.md', '.txt', '.js', '.json', '.csv', '.yml', '.yaml', '.toml', '.cfg', '.ini', '.conf', '.sh', '.bat', '.ps1']);

function extractFrontmatter(content, ext) {
  if (ext === '.py') {
    const match = content.match(/^\uFEFF?\s*"""([\s\S]*?)"""/);
    if (match) return match[1].trim();
  }
  if (ext === '.md' || ext === '.txt') {
    const match = content.match(/^---\s*\n([\s\S]*?)---\s*\n/);
    if (match) return match[1].trim();
  }
  return '';
}

const KEY_RE = /^([A-Za-z\u00C0-\u024F][\w\u00C0-\u024F]*?(?:\s+[A-Za-z\u00C0-\u024F][\w\u00C0-\u024F]*){0,2}):\s*(.*)$/;

function parseKeys(fm) {
  const lines = fm.split('\n');
  const result = {};
  const descLines = [];
  let currentKey = null;
  let currentVal = [];
  let inDesc = true;

  for (const line of lines) {
    const t = line.trim();
    if (!t) { inDesc = false; continue; }

    const keyMatch = t.match(KEY_RE);
    if (keyMatch) {
      const rawKey = keyMatch[1].trim();
      // heuristic: label keys are ≤18 chars; longer means it's prose with a colon
      if (rawKey.length <= 18) {
        inDesc = false;
        if (currentKey) result[currentKey] = currentVal.join(' ').trim();
        currentKey = rawKey.toLowerCase().replace(/[\s\/]+/g, '_');
        currentVal = keyMatch[2].trim() ? [keyMatch[2].trim()] : [];
      } else {
        if (inDesc) descLines.push(t);
        else if (currentKey) currentVal.push(t);
      }
    } else if (inDesc) {
      descLines.push(t);
    } else if (currentKey) {
      currentVal.push(t);
    }
  }
  if (currentKey) result[currentKey] = currentVal.join(' ').trim();

  const desc = descLines.join(' ').trim();
  if (desc) result.description = desc;

  return result;
}

function quote(val) {
  const s = String(val);
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function main() {
  const entries = fs.readdirSync('.');
  const rows = [];
  const allKeys = new Set();

  for (const entry of entries) {
    if (SKIP.has(entry) || entry.startsWith('.')) continue;
    const stat = fs.statSync(entry);
    if (!stat.isFile()) continue;
    const ext = path.extname(entry).toLowerCase();
    if (!TEXT_EXTS.has(ext)) continue;

    const content = fs.readFileSync(entry, 'utf-8');
    const fm = extractFrontmatter(content, ext);
    if (!fm) continue;

    const parsed = parseKeys(fm);
    parsed._file = entry;
    rows.push(parsed);
    Object.keys(parsed).forEach(k => allKeys.add(k));
  }

  const sortedKeys = ['_file', ...[...allKeys].filter(k => k !== '_file').sort()];

  let csv = sortedKeys.map(quote).join(',') + '\n';
  for (const row of rows) {
    csv += sortedKeys.map(k => quote(row[k] || '')).join(',') + '\n';
  }

  fs.writeFileSync('frontmatter_export.csv', csv, 'utf-8');
  console.log('Wrote frontmatter_export.csv with ' + rows.length + ' rows and ' + sortedKeys.length + ' columns');
}

main();
