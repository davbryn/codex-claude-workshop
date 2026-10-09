// Bundles src/ into one self-contained index.html (works offline, from file://, GitHub Pages, or as an Artifact).
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const read = f => fs.readFileSync(path.join(root, f), 'utf8');
const order = ['physics', 'levels', 'audio', 'art', 'fx', 'gl', 'gemily', 'main'];
let par = {};
try { par = JSON.parse(read('tools/par.json')); } catch (e) { /* formula fallback */ }
let js = '';
for (const f of order) {
  js += `/* ---- ${f}.js ---- */\n` + read(`src/js/${f}.js`) + '\n';
  if (f === 'levels') js += `window.G.PAR = ${JSON.stringify(par)};\n`;
}
js = js.replace(/<\/script>/gi, '<\\/script>');
const html = read('src/index.html').replace('<!--JS-->', () => `<script>\n${js}</script>`);
fs.writeFileSync(path.join(root, 'index.html'), html);
console.log('built index.html', (html.length / 1024).toFixed(0) + ' KB');
