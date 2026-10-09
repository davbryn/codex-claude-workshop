const { chromium } = require('/opt/node-tools/node_modules/playwright');
const out = process.argv[2] || '/tmp/claude-0/shots';
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'] });
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  const errs = [];
  page.on('console', m => { if (['error', 'warning'].includes(m.type())) errs.push(m.type() + ': ' + m.text()); });
  page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message + '\n' + (e.stack || '').split('\n').slice(0, 4).join('\n')));
  await page.goto('file:///home/user/codex-claude-workshop/gemily-lemon/index.html');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: out + '/01-title.png' });
  await page.click('#btnContinue', { force: true });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: out + '/02-story.png' });
  await page.click('#storySkip', { force: true });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: out + '/03-level1.png' });
  // drag shot at first fruit: use solver-ish aim from the hook
  const info = await page.evaluate(() => { const w = window.__game.world; const c = w.cue; const f = w.fruits()[0]; const r = document.getElementById('stage').getBoundingClientRect(); return { c: { x: c.x, y: c.y }, f: { x: f.x, y: f.y }, r: { l: r.left, t: r.top, w: r.width, h: r.height } }; });
  const toS = (p) => ({ x: info.r.l + p.x / 720 * info.r.w, y: info.r.t + p.y / 1040 * info.r.h });
  const ang = Math.atan2(info.f.y - info.c.y, info.f.x - info.c.x);
  const s0 = toS({ x: info.c.x, y: info.c.y });
  const pull = 110;
  await page.mouse.move(s0.x, s0.y); await page.mouse.down();
  await page.mouse.move(s0.x - Math.cos(ang) * pull * 0.5, s0.y - Math.sin(ang) * pull * 0.5, { steps: 5 });
  await page.mouse.move(s0.x - Math.cos(ang) * pull, s0.y - Math.sin(ang) * pull, { steps: 5 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: out + '/04-aim.png' });
  await page.mouse.up();
  for (let i = 0; i < 6; i++) { await page.waitForTimeout(260); await page.screenshot({ path: out + `/05-roll${i}.png` }); }
  await page.waitForTimeout(3500);
  await page.screenshot({ path: out + '/06-after.png' });
  console.log('phase', await page.evaluate(() => window.__game.phase), 'fruits', await page.evaluate(() => window.__game.world.fruitCount()));
  console.log('errors', errs);
  await b.close();
})();
