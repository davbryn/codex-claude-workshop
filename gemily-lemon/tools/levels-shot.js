const { chromium } = require('/opt/node-tools/node_modules/playwright');
const out = '/tmp/claude-0/shots';
const levels = process.argv.slice(2).map(Number);
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message)); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto('file:///home/user/codex-claude-workshop/gemily-lemon/index.html');
  await page.waitForTimeout(1000);
  for (const n of levels) {
    await page.evaluate(n => window.__game.startLevel(n), n);
    await page.waitForTimeout(2600);
    await page.screenshot({ path: `${out}/lv${n}.png`, clip: { x: 0, y: 90, width: 390, height: 520 } });
  }
  console.log(errs);
  await b.close();
})();
