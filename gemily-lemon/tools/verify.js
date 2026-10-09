// Proves levels are solvable: replays the built-in solver shot by shot and reports how many shots each level needs.
// usage: node tools/verify.js [from] [to] [--write]
const fs = require('fs'), path = require('path'), vm = require('vm');
const ctx = { performance }; ctx.globalThis = ctx; vm.createContext(ctx);
for (const f of ['physics.js', 'levels.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/js', f), 'utf8'), ctx);
const G = ctx.G;
const from = +process.argv[2] || 1, to = +process.argv[3] || 12;
const out = {};
for (let n = from; n <= to; n++) {
  const lvl = G.makeLevel(n), w = new G.World(lvl);
  w.emit = false;
  let shots = 0, log = [];
  const t0 = Date.now();
  while (w.fruitCount() > 0 && shots < 16) {
    const best = G.findBestShot(w);
    w.shoot(best.angle, best.power);
    for (let i = 0; i < 2400 && !(w.isSettled() && i > 20); i++) w.step();
    shots++; log.push(best.pops);
  }
  out[n] = Math.max(2, shots + 1);
  console.log(`L${String(n).padStart(2)} ${G.WORLDS[lvl.world].name.padEnd(13)} fruits=${String(lvl.count).padStart(2)} boss=${lvl.boss ? 'Y' : '-'} solved=${w.fruitCount() === 0} shots=${shots} par(formula)=${lvl.par} pops/shot=[${log}] ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}
if (process.argv.includes('--write')) fs.writeFileSync(path.join(__dirname, 'par.json'), JSON.stringify(out));
