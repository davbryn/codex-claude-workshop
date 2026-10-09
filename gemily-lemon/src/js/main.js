/* Gemily Lemon's Last Stand - game loop, rendering, input, UI flow. */
(function () {
  'use strict';
  const G = window.G, TB = G.TABLE, W = TB.W, H = TB.H, A = G.Audio, FX = G.FX, Art = G.Art, Gem = G.Gemily;
  const $ = id => document.getElementById(id);
  const TAU = Math.PI * 2, R = (a, b) => a + Math.random() * (b - a), clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const INK = '#2a0f3a';

  // ------------------------------------------------------------ save
  const Save = {
    d: { stars: {}, best: {}, unlocked: 1, total: 0, music: true, sfx: true, seen: false },
    load() { try { const j = JSON.parse(localStorage.getItem('gemily-lemon-v1') || 'null'); if (j) Object.assign(this.d, j); } catch (e) { /* private mode */ } },
    save() { try { localStorage.setItem('gemily-lemon-v1', JSON.stringify(this.d)); } catch (e) { /* ignore */ } }
  };
  Save.load();
  A.musicOn = Save.d.music; A.sfxOn = Save.d.sfx;

  // ------------------------------------------------------------ canvases + layout
  const app = $('app'), stage = $('stage');
  let display = $('gl'), dctx = null;
  const scene = document.createElement('canvas');
  const sctx = scene.getContext('2d', { alpha: false });
  let tableCv = document.createElement('canvas');
  let pxs = 1, stageScale = 1, useGL = false;

  FX.init(W, H, 1);
  if (G.GL.init(display)) useGL = true;
  else { const n = display.cloneNode(); display.replaceWith(n); display = n; dctx = n.getContext('2d'); }

  function layout() {
    const ar = app.getBoundingClientRect(), vw = ar.width, vh = ar.height;
    const top = $('top').offsetHeight + $('subbar').offsetHeight, bot = $('bottom').offsetHeight;
    const avail = vh - top - bot;
    const s = Math.min(vw / W, avail / H);
    stageScale = s;
    stage.style.width = (W * s) + 'px'; stage.style.height = (H * s) + 'px';
    stage.style.left = ((vw - W * s) / 2) + 'px'; stage.style.top = (top + (avail - H * s) / 2) + 'px';
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let k = clamp(s * dpr, 0.5, 2.2);
    while (W * k * H * k > 1.6e6) k *= 0.93;
    if (Math.abs(k - pxs) > 0.02 || !scene.width) {
      pxs = k; scene.width = Math.round(W * pxs); scene.height = Math.round(H * pxs);
      FX.resize(pxs); buildTable();
      if (!useGL) { display.width = scene.width; display.height = scene.height; }
    }
  }

  // ------------------------------------------------------------ game state
  let world = null, level = null, n = 1, phase = 'boot';   // boot | title | aim | roll | clear | story
  let par = 3, hintsLeft = 3, zest = 1, zestMode = false, rescueUsed = false, hint = null, solver = null;
  let aim = null, fast = false, acc = 0, time = 0, rollT = 0, chainN = 0, chainShow = 0, totalScore = Save.d.total || 0;
  let paused = false, rainbow = 0, slotOpen = false, goldPopped = false, attractN = 3, levelFlash = 0;
  const attract = { stage: 'wait', t: 2 };
  const trail = [];
  const byId = new Map();

  const WT = () => G.WORLDS[level ? level.world : 0];

  // ------------------------------------------------------------ static table
  function rr(x, x0, y0, w, h, r) {
    x.beginPath(); x.moveTo(x0 + r, y0); x.arcTo(x0 + w, y0, x0 + w, y0 + h, r); x.arcTo(x0 + w, y0 + h, x0, y0 + h, r); x.arcTo(x0, y0 + h, x0, y0, r); x.arcTo(x0, y0, x0 + w, y0, r); x.closePath();
  }
  function buildTable() {
    const wt = WT(), lv = level || { world: 0, blocks: [], zones: [] };
    const c = tableCv; c.width = scene.width; c.height = scene.height;
    const x = c.getContext('2d'); x.setTransform(pxs, 0, 0, pxs, 0, 0);
    const { L, T, R: RR, B } = TB;
    // outer rim
    const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, wt.rim[0]); g.addColorStop(1, wt.rim[1]);
    rr(x, 6, 6, W - 12, H - 12, 56); x.fillStyle = g; x.fill(); x.lineWidth = 6; x.strokeStyle = wt.rimEdge; x.stroke();
    rr(x, 16, 16, W - 32, H - 32, 46); x.lineWidth = 3; x.strokeStyle = 'rgba(255,255,255,.55)'; x.stroke();
    // rim sights
    x.fillStyle = '#fff'; x.strokeStyle = wt.rimEdge; x.lineWidth = 2;
    const dot = (px, py) => { x.beginPath(); x.arc(px, py, 6, 0, TAU); x.fill(); x.stroke(); };
    for (let i = 1; i < 8; i++) { const px = L + (RR - L) * i / 8; dot(px, 29); dot(px, H - 29); }
    for (let i = 1; i < 8; i++) { if (i === 4) continue; const py = T + (B - T) * i / 8; dot(29, py); dot(W - 29, py); }
    // felt
    const f = x.createLinearGradient(0, T, 0, B); f.addColorStop(0, wt.felt[0]); f.addColorStop(1, wt.felt[1]);
    x.fillStyle = f; x.fillRect(L, T, RR - L, B - T);
    x.save(); x.beginPath(); x.rect(L, T, RR - L, B - T); x.clip();
    const rg = x.createRadialGradient(W / 2, H * 0.45, 40, W / 2, H * 0.45, 640); rg.addColorStop(0, 'rgba(255,255,255,.22)'); rg.addColorStop(1, 'rgba(0,0,0,.16)');
    x.fillStyle = rg; x.fillRect(L, T, RR - L, B - T);
    x.strokeStyle = 'rgba(255,255,255,.075)'; x.lineWidth = 2;
    for (let i = -20; i < 40; i++) { x.beginPath(); x.moveTo(L + i * 64, T); x.lineTo(L + i * 64 + 1000, T + 1000); x.stroke(); x.beginPath(); x.moveTo(L + i * 64 + 1000, T); x.lineTo(L + i * 64, T + 1000); x.stroke(); }
    // baulk line + head spot
    x.strokeStyle = 'rgba(255,255,255,.22)'; x.lineWidth = 3; x.beginPath(); x.moveTo(L, 770); x.lineTo(RR, 770); x.stroke();
    x.beginPath(); x.arc(W / 2, 770, 90, 0, Math.PI); x.stroke();
    x.fillStyle = 'rgba(255,255,255,.35)'; x.beginPath(); x.arc(W / 2, 860, 8, 0, TAU); x.fill();
    // inner shadow along cushions
    const sh = (x0, y0, x1, y1, rx, ry, rw, rh) => { const gg = x.createLinearGradient(x0, y0, x1, y1); gg.addColorStop(0, 'rgba(0,0,0,.34)'); gg.addColorStop(1, 'rgba(0,0,0,0)'); x.fillStyle = gg; x.fillRect(rx, ry, rw, rh); };
    sh(L, 0, L + 30, 0, L, T, 30, B - T); sh(RR, 0, RR - 30, 0, RR - 30, T, 30, B - T); sh(0, T, 0, T + 30, L, T, RR - L, 30); sh(0, B, 0, B - 30, L, B - 30, RR - L, 30);
    // zones
    for (const z of lv.zones || []) {
      rr(x, z.x - z.w / 2, z.y - z.h / 2, z.w, z.h, 44);
      if (z.kind === 'ice') {
        const zg = x.createLinearGradient(z.x - z.w / 2, z.y - z.h / 2, z.x + z.w / 2, z.y + z.h / 2); zg.addColorStop(0, 'rgba(220,252,255,.65)'); zg.addColorStop(1, 'rgba(140,220,255,.45)');
        x.fillStyle = zg; x.fill(); x.lineWidth = 4; x.strokeStyle = 'rgba(255,255,255,.85)'; x.stroke();
        x.strokeStyle = 'rgba(255,255,255,.7)'; x.lineWidth = 3; x.lineCap = 'round';
        for (let i = 0; i < 5; i++) { const sx = z.x - z.w / 2 + 30 + i * 46, sy = z.y - z.h / 2 + 24 + (i % 3) * 40; x.beginPath(); x.moveTo(sx, sy); x.lineTo(sx + 28, sy - 20); x.stroke(); }
        x.font = '900 26px Arial'; x.fillStyle = 'rgba(255,255,255,.7)'; x.textAlign = 'center'; x.fillText('ICE', z.x, z.y + 8);
      } else {
        x.fillStyle = 'rgba(255,110,190,.42)'; x.fill(); x.lineWidth = 4; x.strokeStyle = 'rgba(255,200,235,.9)'; x.stroke();
        x.fillStyle = 'rgba(255,255,255,.45)';
        for (let i = 0; i < 6; i++) { x.beginPath(); x.ellipse(z.x - z.w / 2 + 34 + (i % 3) * 66, z.y - z.h / 2 + 34 + Math.floor(i / 3) * 76, 15, 9, -0.5, 0, TAU); x.fill(); }
        x.font = '900 24px Arial'; x.fillStyle = 'rgba(255,255,255,.75)'; x.textAlign = 'center'; x.fillText('JELLY', z.x, z.y + 8);
      }
    }
    x.restore();
    // blocks
    for (const b of lv.blocks || []) {
      rr(x, b.x - b.w / 2, b.y - b.h / 2 + 5, b.w, b.h, 10); x.fillStyle = 'rgba(0,0,0,.28)'; x.fill();
      const bg = x.createLinearGradient(0, b.y - b.h / 2, 0, b.y + b.h / 2); bg.addColorStop(0, wt.rim[0]); bg.addColorStop(1, wt.rim[1]);
      rr(x, b.x - b.w / 2, b.y - b.h / 2, b.w, b.h, 10); x.fillStyle = bg; x.fill(); x.lineWidth = 4; x.strokeStyle = wt.rimEdge; x.stroke();
      x.fillStyle = 'rgba(255,255,255,.5)'; rr(x, b.x - b.w / 2 + 6, b.y - b.h / 2 + 4, b.w - 12, 5, 3); x.fill();
    }
    // pockets
    for (const p of TB.POCKETS) {
      x.fillStyle = wt.rimEdge; x.beginPath(); x.arc(p.x, p.y, 49, 0, TAU); x.fill();
      const pg = x.createRadialGradient(p.x, p.y, 4, p.x, p.y, 44); pg.addColorStop(0, '#08020f'); pg.addColorStop(0.75, '#1a0830'); pg.addColorStop(1, '#3a1458');
      x.fillStyle = pg; x.beginPath(); x.arc(p.x, p.y, 43, 0, TAU); x.fill();
      x.strokeStyle = 'rgba(255,255,255,.28)'; x.lineWidth = 4; x.beginPath(); x.arc(p.x, p.y, 45, 0, TAU); x.stroke();
    }
  }

  // ------------------------------------------------------------ faces / visual state
  function vis(b) {
    if (b.v) return b.v;
    b.maxHp = b.maxHp || G.FRUITS[b.type].hp;
    return (b.v = { t: Math.random() * 10, blink: 0, blinkAnim: 0, blinkT: R(0.4, 3.5), look: { x: 0, y: 0.3 }, lookT: R(0.2, 2), lookId: null, lookDir: null,
      mood: 'idle', moodT: 0, squash: 0, sa: 0, phase: Math.random() * TAU, smirk: false, smirkT: 0, scareT: -1, scareDur: 0.6, scareAng: 0, hop: 0 });
  }
  function pickLook(b, v) {
    const r = Math.random();
    const others = world.bodies.filter(o => o.alive && o !== b && o.type !== 'pit' && Math.hypot(o.x - b.x, o.y - b.y) < 430);
    if (r < 0.62 && others.length) {
      others.sort((p, q) => Math.hypot(p.x - b.x, p.y - b.y) - Math.hypot(q.x - b.x, q.y - b.y));
      const o = others[Math.floor(Math.random() * Math.min(3, others.length))];
      v.lookId = o.id; v.lookDir = null; v.lookT = R(1.1, 2.8);
      if (o.type !== 'lemon' && Math.random() < 0.6) {
        const ov = vis(o);
        if (ov.mood === 'idle') {   // they look right back at each other, sometimes smirking
          ov.lookId = b.id; ov.lookDir = null; ov.lookT = v.lookT;
          if (Math.random() < 0.5) { v.smirk = ov.smirk = true; v.smirkT = ov.smirkT = v.lookT; }
        }
      }
    } else if (r < 0.82) { const a = Math.random() * TAU; v.lookDir = { x: Math.cos(a), y: Math.sin(a) }; v.lookId = null; v.lookT = R(0.6, 1.6); }
    else { v.lookDir = { x: 0, y: 0.5 }; v.lookId = null; v.lookT = R(0.8, 2.2); }
  }
  function updateFaces(dt) {
    if (!world) return;
    byId.clear();
    for (const b of world.bodies) byId.set(b.id, b);
    for (const b of world.bodies) {
      if (!b.alive || b.type === 'pit') continue;
      const v = vis(b);
      v.t += dt;
      // blink
      if (v.blinkAnim > 0) { v.blinkAnim -= dt; v.blink = Math.sin(Math.PI * clamp(1 - v.blinkAnim / 0.17, 0, 1)); if (v.blinkAnim <= 0) { v.blink = 0; } }
      else { v.blinkT -= dt; if (v.blinkT <= 0) { v.blinkAnim = 0.17; v.blinkT = Math.random() < 0.2 ? 0.25 : R(1.6, 4.4); } }
      // look
      v.lookT -= dt; if (v.lookT <= 0) pickLook(b, v);
      if (v.smirkT > 0) { v.smirkT -= dt; if (v.smirkT <= 0) v.smirk = false; }
      // delayed scare (blast wave reaching me)
      if (v.scareT >= 0) { v.scareT -= dt; if (v.scareT < 0) { v.mood = 'scared'; v.moodT = v.scareDur; v.squash = 0.14; v.sa = v.scareAng; } }
      if (v.moodT > 0) { v.moodT -= dt; if (v.moodT <= 0) v.mood = 'idle'; }
      if (b.fuse >= 0) v.mood = 'panic';
      else if (v.mood === 'panic') { v.mood = 'idle'; }
      v.squash *= Math.pow(0.0006, dt);
      // desired gaze
      let tx = 0, ty = 0.2;
      const sp = Math.hypot(b.vx, b.vy);
      if (b.type === 'lemon' && aim && aim.active && aim.len > 20) { tx = Math.cos(aim.ang); ty = Math.sin(aim.ang); v.mood = 'focus'; v.moodT = 0.12; }
      else if (sp > 60) { tx = b.vx / sp; ty = b.vy / sp; }
      else if (v.lookId && byId.get(v.lookId)) { const o = byId.get(v.lookId), dx = o.x - b.x, dy = o.y - b.y, d = Math.hypot(dx, dy) || 1; tx = dx / d; ty = dy / d; }
      else if (v.lookDir) { tx = v.lookDir.x; ty = v.lookDir.y; }
      v.look.x += (tx - v.look.x) * Math.min(1, dt * 12); v.look.y += (ty - v.look.y) * Math.min(1, dt * 12);
    }
    for (const bp of world.bumpers) if (bp.pulse > 0) bp.pulse = Math.max(0, bp.pulse - dt * 4);
  }
  function scareAround(x, y, radius, strong) {
    for (const o of world.bodies) {
      if (!o.alive || o.type === 'pit') continue;
      const d = Math.hypot(o.x - x, o.y - y);
      if (d < radius && d > 1) { const v = vis(o); if (v.scareT < 0 && v.mood !== 'panic') { v.scareT = d / 1100; v.scareDur = strong ? 0.9 : 0.6; v.scareAng = Math.atan2(o.y - y, o.x - x); } }
    }
  }

  // ------------------------------------------------------------ world events -> juice
  function handleEvents() {
    const evs = world.events; if (!evs.length) return;
    for (const e of evs) {
      switch (e.t) {
        case 'shoot': A.launch(e.power); FX.kick(3 + e.power * 6, 0, 0.002); FX.ring(e.x, e.y, 90, '#fff7a0', 6, 0.3); A.setIntensity(2); break;
        case 'hit': {
          A.hit(e.speed);
          const va = e.a.type !== 'pit' ? vis(e.a) : null, vb = e.b.type !== 'pit' ? vis(e.b) : null;
          const sq = clamp(e.speed / 1500, 0.05, 0.36), an = Math.atan2(e.ny, e.nx);
          if (va) { va.squash = Math.max(va.squash, sq); va.sa = an; if (e.speed > 220 && e.a.type !== 'lemon') { va.mood = 'ouch'; va.moodT = 0.45; } }
          if (vb) { vb.squash = Math.max(vb.squash, sq); vb.sa = an; if (e.speed > 220 && e.b.type !== 'lemon') { vb.mood = 'ouch'; vb.moodT = 0.45; } }
          if (e.speed > 180) { FX.sparks(e.x, e.y, 5, 260, '#fff'); FX.kick(Math.min(10, e.speed / 120), 0, 0); }
          if (e.speed > 400) FX.ring(e.x, e.y, 46, '#fff', 4, 0.25);
          break;
        }
        case 'wall': A.wall(e.speed); FX.sparks(e.x, e.y, 3, 160, '#fff'); if (e.speed > 400) FX.kick(2, 0, 0); break;
        case 'hurt': { const v = vis(e.b); v.mood = 'ouch'; v.moodT = 0.7; v.squash = 0.3; A.hit(900); FX.kick(10, 0.06, 0.004); FX.drops(e.b.x, e.b.y, e.b.type, 8, 280); FX.text(e.b.x, e.b.y - e.b.r - 10, e.b.type === 'boss' ? 'OW!!' : 'OOF!', { size: 34, col: '#ffd23c', life: 0.6 }); if (e.b.type === 'boss') { FX.ripple(e.b.x, e.b.y, 0.9); FX.chunks('melon', e.b.x, e.b.y, 5, 340); } break; }
        case 'prime': A.prime(); { const v = vis(e.b); v.mood = 'panic'; } FX.sparks(e.b.x, e.b.y - e.b.r, 3, 160, '#ffd54a'); break;
        case 'beam': FX.beam(e.x, e.y, e.ang, e.len); A.beam(); FX.kick(8, 0.12, 0.006); break;
        case 'pitpop': FX.sparks(e.x, e.y, 6, 300, '#c08a50'); break;
        case 'bump': A.bump(); e.bp.pulse = 1; FX.ring(e.bp.x, e.bp.y, 60, '#fff', 5, 0.3); FX.sparks(e.bp.x, e.bp.y, 4, 300, '#ffe66b'); FX.kick(3, 0, 0); break;
        case 'portal': A.portal(); FX.ring(e.fx, e.fy, 70, '#c9a8ff', 6, 0.4); FX.ring(e.tx, e.ty, 70, '#8fe8ff', 6, 0.4); FX.sparks(e.tx, e.ty, 12, 380, '#bfe9ff'); FX.ripple(e.tx, e.ty, 0.6); break;
        case 'scratch': A.scratch(); FX.text(e.x, e.y - 60, 'SCRATCH!', { size: 44, col: '#ff7ab8' }); FX.kick(10, 0.1, 0.004); FX.ring(e.x, e.y, 80, '#ff7ab8', 6, 0.5);
          for (const o of world.bodies) if (o.alive && o.type !== 'lemon' && o.type !== 'pit') { const v = vis(o); v.mood = 'idle'; v.smirk = true; v.smirkT = 2; }
          if (phase === 'roll') Gem.say(G.pick(G.LINES.scratch), { mood: 'shock' }); break;
        case 'respawn': FX.ring(e.x, e.y, 70, '#fff7a0', 6, 0.4); FX.sparks(e.x, e.y, 14, 300, '#fff7a0'); A.ui(); break;
        case 'pocket': A.pocket(); FX.text(e.x < 360 ? e.x + 100 : e.x - 100, e.y + (e.y < 300 ? 90 : -90), 'POCKETED x2', { size: 32, col: '#8fe8ff', life: 1 }); break;
        case 'mega': A.mega(); FX.kick(10, 0.3, 0.01); FX.text(360, 500, 'MEGA SQUEEZE!', { size: 68, col: '#ff5fd0', life: 1.4 }); break;
        case 'zest': A.zest(); break;
        case 'boom': {
          chainN = e.n; chainShow = 1.6;
          A.pop(e.type, e.depth);
          FX.explode(e);
          scareAround(e.x, e.y, 330, e.type === 'boss' || e.type === 'melon');
          const wrd = e.gold ? 'x5 ' : '';
          FX.text(e.x + R(-18, 18), e.y + 8, wrd + '+' + e.pts, { size: e.gold ? 44 : 28 + Math.min(14, e.depth * 2), col: e.gold ? '#ffe35a' : '#ffffff', life: 0.95, vy: -90 });
          if (e.gold) { A.gold(); goldPopped = true; FX.text(360, 400, 'GOLDEN!', { size: 70, col: '#ffe35a', life: 1.2 }); FX.rain(60); }
          if (e.n === 3) FX.text(360, 250, 'CHAIN!', { size: 62, col: '#ffe35a', life: 1.1 });
          if (e.n === 6) { FX.text(360, 250, 'SUPER CHAIN!', { size: 64, col: '#ff9ad0', life: 1.2 }); FX.rain(30); }
          if (e.n === 10) { FX.text(360, 250, 'JUICE MASTER!', { size: 64, col: '#8fffcf', life: 1.4 }); FX.rain(60); rainbow = 1; }
          if (e.n === 15) { FX.text(360, 250, 'FRUITPOCALYPSE!', { size: 62, col: '#ff6a4a', life: 1.5 }); FX.rain(80); rainbow = 1.2; }
          A.setIntensity(e.n >= 7 ? 3 : e.n >= 3 ? 3 : 2);
          if (e.type === 'boss') { FX.confetti(e.x, e.y, 120, 900); FX.rain(100); FX.kick(34, 0.6, 0.014); }
          // last fruit: slow-mo kill cam
          if (world.fruitCount() === 0) { FX.slow = 1.0; FX.kick(20, 0.35, 0.01); FX.ripple(e.x, e.y, 1.2); FX.confetti(e.x, e.y, 80, 800); A.slowmo(); }
          break;
        }
      }
    }
    evs.length = 0;
  }

  // ------------------------------------------------------------ turn flow
  function setPhase(p) { phase = p; document.body.dataset.phase = p; }
  function updateHud(force) {
    if (!world) return;
    $('score').textContent = Math.round(totalScore + world.score).toLocaleString();
    $('nFruit').textContent = world.fruitCount();
    $('nShots').textContent = world.shots; $('nPar').textContent = par;
    const st = world.shots <= par ? 3 : world.shots <= par + 2 ? 2 : 1;
    const stars = $('starsBox').children;
    for (let i = 0; i < 3; i++) stars[i].classList.toggle('on', i < (rescueUsed ? 1 : st));
    $('lvlName').textContent = (level.boss ? '👑 ' : '') + 'LEVEL ' + n;
    $('worldName').textContent = level.boss ? 'BOSS: BIG MELON' : level.name;
    $('hintN').textContent = hintsLeft; $('zestN').textContent = zest;
    $('btnHint').disabled = hintsLeft <= 0 || phase !== 'aim'; $('btnZest').disabled = zest <= 0 || phase !== 'aim';
    $('btnMega').hidden = !(phase === 'aim' && world.shots >= par + 3 && world.fruitCount() > 0);
    $('btnZest').classList.toggle('active', zestMode);
    stage.classList.toggle('zesting', zestMode);
  }

  function resolveShot() {
    const pops = world.shotPops;
    hint = null;
    if (world.fruitCount() === 0) { levelClear(); return; }
    A.setIntensity(1);
    const finish = () => {
      setPhase('aim'); updateHud();
      if (world.shots >= par + 3 && !rescueUsed && !world._rescueSaid) { world._rescueSaid = true; Gem.say(G.LINES.rescue, { mood: 'smug' }); }
    };
    // Gemily reacts
    const lines = G.LINES;
    if (pops >= 10) { Gem.say(G.pick(lines.chain10), { mood: 'happy' }); }
    else if (pops >= 6) { Gem.say(G.pick(lines.chain6), { mood: 'happy' }); }
    else if (pops >= 3) { Gem.say(G.pick(lines.chain3), { mood: 'happy' }); }
    else if (pops === 0) { Gem.say(G.pick(lines.miss), { mood: 'talk' }); }
    if (pops >= 3) { const lm = vis(world.cue); lm.mood = 'happy'; lm.moodT = 2; }
    if (pops >= 5 || goldPopped) { goldPopped = false; setPhase('slot'); showSlot(pops).then(finish); }
    else finish();
  }

  function levelClear() {
    setPhase('clear');
    let stars = world.shots <= par ? 3 : world.shots <= par + 2 ? 2 : 1;
    if (rescueUsed) stars = 1;
    const bonus = stars * 500 + (world.shots <= par ? 250 : 0);
    const gain = Math.round(world.score + bonus);
    totalScore += gain; Save.d.total = totalScore;
    const prev = Save.d.stars[n] || 0, first = prev === 0;
    Save.d.stars[n] = Math.max(prev, stars);
    Save.d.best[n] = Math.max(Save.d.best[n] || 0, Math.round(world.score + bonus));
    Save.d.unlocked = Math.max(Save.d.unlocked, n + 1);
    Save.save();
    A.setIntensity(3);
    Gem.mood('happy');
    const lm = vis(world.cue); lm.mood = 'happy'; lm.moodT = 99;
    FX.rain(120); FX.kick(0, 0.2, 0);
    setTimeout(() => {
      A.fanfare();
      $('clTitle').textContent = stars === 3 ? 'PERFECT!' : 'TABLE CLEARED!';
      $('clLevel').textContent = 'Level ' + n + ' · ' + level.name;
      $('clScore').textContent = '+' + gain.toLocaleString();
      $('clShots').textContent = world.shots + (world.shots === 1 ? ' shot' : ' shots') + ' (par ' + par + ')';
      $('clBest').textContent = first ? 'New level conquered!' : (gain >= Save.d.best[n] ? 'New best!' : 'Best ' + Save.d.best[n].toLocaleString());
      const sEls = $('clStars').children;
      for (let i = 0; i < 3; i++) { sEls[i].classList.remove('on'); setTimeout(() => { if (i < stars) { sEls[i].classList.add('on'); A.star(i); FX.kick(6, 0.1, 0.004); FX.confetti(360, 380, 14, 500, 1.2); } }, 500 + i * 420); }
      show('sClear'); $('clBubble').appendChild($('bubble'));
      Gem.say(stars === 3 ? G.pick(G.LINES.clear3) : G.pick(G.LINES.clear), { mood: 'happy', hold: 4000 });
    }, 1500);
  }

  const SYM = ['🍎', '🍊', '🍒', '🍌', '🌶️', '🍍', '🍋', '⭐'];
  function showSlot(pops) {
    return new Promise(res => {
      slotOpen = true;
      const ov = $('sSlot'), reels = [$('reel0'), $('reel1'), $('reel2')], msg = $('slotMsg');
      msg.textContent = pops >= 10 ? 'MEGA CHAIN BONUS!' : 'CHAIN BONUS SPIN!'; msg.className = '';
      // decide outcome
      const r = Math.random(); let out;
      const s0 = Math.floor(Math.random() * SYM.length);
      if (r < 0.14 + Math.min(0.2, pops * 0.012)) out = [s0, s0, s0];
      else if (r < 0.55) { const a = Math.floor(Math.random() * SYM.length); let b = Math.floor(Math.random() * SYM.length); if (b === a) b = (b + 1) % SYM.length; out = [a, a, b]; }
      else { const a = Math.floor(Math.random() * SYM.length); out = [a, (a + 2) % SYM.length, (a + 5) % SYM.length]; }
      const stopped = [false, false, false]; let skip = false, tickN = 0;
      ov.classList.add('open'); ov.hidden = false;
      reels.forEach(rl => rl.classList.add('spin'));
      const iv = setInterval(() => { reels.forEach((rl, i) => { if (!stopped[i]) rl.firstElementChild.textContent = SYM[Math.floor(Math.random() * SYM.length)]; }); A.slotTick(tickN++); }, 70);
      const stop = i => { stopped[i] = true; reels[i].classList.remove('spin'); reels[i].firstElementChild.textContent = SYM[out[i]]; A.slotStop(i); FX.kick(4, 0, 0); };
      [900, 1400, 1950].forEach((ms, i) => setTimeout(() => stop(i), ms));
      setTimeout(() => {
        clearInterval(iv);
        const triple = out[0] === out[1] && out[1] === out[2], pair = !triple && (out[0] === out[1] || out[1] === out[2] || out[0] === out[2]);
        let prize = 100, text = '+100';
        if (triple) { prize = out[0] === 6 ? 5000 : 2000; text = (out[0] === 6 ? 'LEMON JACKPOT! +' : 'JACKPOT! +') + prize; zest++; A.jackpot(); FX.rain(150); rainbow = 1.5; msg.className = 'win'; }
        else if (pair) { prize = 400; text = 'PAIR! +400'; A.gold(); msg.className = 'win'; }
        else A.star(0);
        totalScore += prize; Save.d.total = totalScore;
        msg.textContent = text + (triple ? '  +💣' : '');
        reels.forEach(rl => rl.classList.toggle('hit', triple || pair));
        setTimeout(() => { ov.classList.remove('open'); ov.hidden = true; slotOpen = false; reels.forEach(rl => rl.classList.remove('hit')); res(); }, triple ? 1900 : 1200);
      }, 2200);
    });
  }

  function shoot(ang, power) {
    hint = null; solver = null; zestMode = false;
    world.shoot(ang, power);
    setPhase('roll'); rollT = 0; fast = false; chainN = 0;
    $('hintN').parentElement.blur();
    updateHud();
  }
  function doZest(f) {
    zest--; zestMode = false; setPhase('roll'); rollT = 0; chainN = 0; hint = null;
    world.zestBomb(f);
    updateHud();
  }
  function doMega() {
    if (phase !== 'aim') return;
    rescueUsed = true; setPhase('roll'); rollT = 0; chainN = 0; hint = null;
    Gem.say('MEGA SQUEEZE! Everybody out of the pool!', { mood: 'happy' });
    world.megaSqueeze(); updateHud();
  }
  function doHint() {
    if (phase !== 'aim' || hintsLeft <= 0 || solver) return;
    hintsLeft--; A.ui();
    Gem.say(G.pick(G.LINES.hint), { mood: 'talk', hold: 1800 });
    solver = G.makeSolver(world); updateHud();
  }

  // ------------------------------------------------------------ level start
  function startLevel(num) {
    n = Math.max(1, num | 0);
    level = G.makeLevel(n);
    world = new G.World(level);
    world.bumpers.forEach(b => { b.pulse = 0; });
    par = level.par; hintsLeft = 3; zest = 1; zestMode = false; rescueUsed = false; hint = null; solver = null; chainN = 0; goldPopped = false; trail.length = 0; aim = null;
    FX.reset(); buildTable();
    const wt = WT();
    document.documentElement.style.setProperty('--bg0', wt.bg[0]); document.documentElement.style.setProperty('--bg1', wt.bg[1]);
    document.documentElement.style.setProperty('--accent', wt.rim[1]);
    hideAll(); setPhase('aim'); updateHud();
    A.play(wt.song, 'game'); A.setIntensity(1);
    FX.text(360, 470, level.boss ? 'BOSS FIGHT!' : 'LEVEL ' + n, { size: 84, col: '#fff7a0', life: 1.5, vy: -20, rot: -0.06 });
    FX.text(360, 548, level.boss ? 'Big Melon & friends' : level.name, { size: 38, col: '#fff', life: 1.4, vy: -20, rot: -0.04 });
    FX.ripple(360, 500, 0.8);
    // Gemily's briefing
    const L = G.LINES; let line = G.pick(L.start);
    const debut = Object.keys(G.DEBUT).find(t => G.DEBUT[t] === n && t !== 'apple');
    if (level.boss) line = G.pick(L.boss);
    else if (debut) line = L['tip' + debut[0].toUpperCase() + debut.slice(1)] || line;
    else if (n === 7) line = L.tipBumper; else if (n === 13) line = L.tipPortal; else if (n === 19) line = L.tipIce;
    else if (level.fruits.some(f => f.gold) && Math.random() < 0.4) line = L.gold;
    if (n === 1) line = 'Pull back anywhere on the table, let go, and Lemmy flies. Pop everything!';
    setTimeout(() => { if (phase === 'aim' && world && level.n === n) Gem.say(line, { mood: 'talk' }); }, 700);
  }

  // ------------------------------------------------------------ attract mode on the title screen
  function startAttract() {
    level = G.makeLevel(attractN); world = new G.World(level); world.bumpers.forEach(b => { b.pulse = 0; });
    FX.reset(); buildTable(); setPhase('title'); attract.stage = 'wait'; attract.t = 2.6; solver = null; aim = null; hint = null;
    const wt = WT();
    document.documentElement.style.setProperty('--bg0', wt.bg[0]); document.documentElement.style.setProperty('--bg1', wt.bg[1]);
    attractN = [3, 7, 4, 9, 13, 5, 10, 8][(attractN + 1) % 8];
  }

  // ------------------------------------------------------------ screens
  const SCREENS = ['sTitle', 'sLevels', 'sClear', 'sPause', 'sStory', 'sSlot'];
  function show(id) { SCREENS.forEach(s => { const el = $(s); if (s === id) { el.hidden = false; requestAnimationFrame(() => el.classList.add('open')); } else { el.classList.remove('open'); if (s !== 'sSlot') el.hidden = true; } }); document.body.classList.toggle('overlay', !!id); }
  function hideAll() { SCREENS.forEach(s => { $(s).classList.remove('open'); $(s).hidden = true; }); document.body.classList.remove('overlay'); }

  function buildLevels() {
    const g = $('lvGrid'); g.innerHTML = '';
    const maxShow = Math.max(36, Save.d.unlocked + 11);
    for (let i = 1; i <= maxShow; i++) {
      if ((i - 1) % 6 === 0) { const wn = G.WORLDS[Math.floor((i - 1) / 6) % 4]; const h = document.createElement('div'); h.className = 'lvWorld'; h.textContent = wn.name + ' — ' + wn.tag; g.appendChild(h); }
      const b = document.createElement('button'); const st = Save.d.stars[i] || 0, locked = i > Save.d.unlocked;
      b.className = 'lvBtn' + (locked ? ' locked' : '') + (i % 6 === 0 ? ' boss' : ''); b.disabled = locked;
      b.innerHTML = (locked ? '🔒' : (i % 6 === 0 ? '👑' : i)) + '<small>' + (locked ? '' : '★'.repeat(st) + '<i>' + '★'.repeat(3 - st) + '</i>') + '</small>';
      b.onclick = () => { A.ui(); startLevel(i); };
      g.appendChild(b);
    }
  }
  function openTitle() {
    Gem.shut(); $('btnContinue').textContent = Save.d.unlocked > 1 ? 'CONTINUE · LEVEL ' + Save.d.unlocked : 'PLAY';
    startAttract(); show('sTitle'); A.play(0, 'menu'); A.setIntensity(1);
  }
  function story() {
    show('sStory');
    const lines = G.LINES.intro; let i = 0;
    const next = () => {
      if (i >= lines.length) { Save.d.seen = true; Save.save(); startLevel(1); return; }
      const t = lines[i++]; $('storyN').textContent = i + '/' + lines.length;
      Gem.say(t, { mood: i === 4 ? 'happy' : 'talk', sticky: true, onDone: () => { $('storyBtn').classList.add('ready'); } });
      $('storyBtn').classList.remove('ready'); $('storyBtn').textContent = i === lines.length ? "LET'S GO!" : 'NEXT ▸';
    };
    $('storyBtn').onclick = () => { A.ui(); next(); };
    $('storySkip').onclick = () => { A.ui(); i = lines.length; next(); };
    // bubble lives in the story screen while it is open
    $('storyBubble').appendChild($('bubble'));
    next();
  }
  function dockBubble() { $('bubbleCol').insertBefore($('bubble'), $('power')); }

  // ------------------------------------------------------------ input
  const DEAD = 22, MAXPULL = 230;
  function toLogical(e) { const r = stage.getBoundingClientRect(); return { x: (e.clientX - r.left) / r.width * W, y: (e.clientY - r.top) / r.height * H }; }
  stage.addEventListener('pointerdown', e => {
    A.init(); A.resume();
    if (!world || paused) return;
    const p = toLogical(e);
    if (phase === 'roll') { fast = true; return; }
    if (phase !== 'aim') return;
    if (zestMode) {
      let best = null, bd = 1e9;
      for (const f of world.fruits()) { const d = Math.hypot(f.x - p.x, f.y - p.y); if (d < f.r + 40 && d < bd) { bd = d; best = f; } }
      if (best) doZest(best);
      return;
    }
    aim = { sx: p.x, sy: p.y, cx: p.x, cy: p.y, active: true, len: 0, ang: -Math.PI / 2, pow: 0, id: e.pointerId, lastTick: 0 };
    try { stage.setPointerCapture(e.pointerId); } catch (er) { /* ignore */ }
    e.preventDefault();
  });
  stage.addEventListener('pointermove', e => {
    if (!aim || !aim.active || e.pointerId !== aim.id) return;
    const p = toLogical(e); aim.cx = p.x; aim.cy = p.y;
    const dx = aim.sx - aim.cx, dy = aim.sy - aim.cy; aim.len = Math.hypot(dx, dy); aim.ang = Math.atan2(dy, dx);
    aim.pow = clamp((aim.len - DEAD) / MAXPULL, 0, 1);
    if (aim.len > DEAD && time - aim.lastTick > 0.06) { A.charge(aim.pow); aim.lastTick = time; }
  });
  function endAim(e, cancel) {
    if (!aim || !aim.active || (e && e.pointerId !== aim.id)) return;
    const a = aim; aim = null; a.active = false;
    if (cancel || phase !== 'aim' || a.len < DEAD + 6) return;
    shoot(a.ang, Math.max(0.08, a.pow));
  }
  stage.addEventListener('pointerup', e => endAim(e, false));
  stage.addEventListener('pointercancel', e => endAim(e, true));
  stage.addEventListener('contextmenu', e => e.preventDefault());
  window.addEventListener('keydown', e => { if (e.key === 'Escape' && phase === 'aim') togglePause(); });

  function togglePause() {
    if (phase === 'title' || phase === 'boot') return;
    paused = !paused;
    if (paused) { show('sPause'); } else { $('sPause').classList.remove('open'); $('sPause').hidden = true; document.body.classList.remove('overlay'); }
    A.ui();
  }
  function syncSnd() {
    $('btnSnd').textContent = (A.musicOn || A.sfxOn) ? '🔊' : '🔇';
    $('tgMusic').textContent = 'Music: ' + (A.musicOn ? 'ON' : 'OFF'); $('tgSfx').textContent = 'Sound FX: ' + (A.sfxOn ? 'ON' : 'OFF');
  }

  function wireUI() {
    $('btnContinue').onclick = () => { A.init(); A.resume(); A.ui(); if (!Save.d.seen) story(); else startLevel(Save.d.unlocked); };
    $('btnLevels').onclick = () => { A.init(); A.resume(); A.ui(); buildLevels(); show('sLevels'); };
    $('lvBack').onclick = () => { A.back(); if (world && phase !== 'title' && phase !== 'boot') { hideAll(); } else openTitle(); };
    $('btnPause').onclick = () => { A.init(); togglePause(); };
    $('btnResume').onclick = () => togglePause();
    $('btnRestart').onclick = () => { paused = false; A.ui(); startLevel(n); };
    $('btnPLevels').onclick = () => { paused = false; A.ui(); buildLevels(); show('sLevels'); };
    $('btnPHome').onclick = () => { paused = false; A.back(); openTitle(); };
    $('btnSnd').onclick = () => { A.init(); const on = !(A.musicOn || A.sfxOn); A.setMusic(on); A.setSfx(on); A.musicOn = A.sfxOn = on; Save.d.music = Save.d.sfx = on; Save.save(); syncSnd(); A.ui(); };
    $('tgMusic').onclick = () => { A.init(); A.musicOn = !A.musicOn; A.setMusic(A.musicOn); Save.d.music = A.musicOn; Save.save(); syncSnd(); A.ui(); };
    $('tgSfx').onclick = () => { A.init(); A.sfxOn = !A.sfxOn; A.setSfx(A.sfxOn); Save.d.sfx = A.sfxOn; Save.save(); syncSnd(); A.ui(); };
    $('btnHint').onclick = doHint;
    $('btnZest').onclick = () => { if (phase !== 'aim' || zest <= 0) return; zestMode = !zestMode; A.ui(); if (zestMode) Gem.say(G.LINES.zest, { mood: 'talk', hold: 2200 }); updateHud(); };
    $('btnMega').onclick = doMega;
    $('clNext').onclick = () => { A.ui(); startLevel(n + 1); };
    $('clReplay').onclick = () => { A.ui(); startLevel(n); };
    $('clMenu').onclick = () => { A.back(); buildLevels(); show('sLevels'); };
    $('sSlot').addEventListener('pointerdown', () => { /* tap to fast-forward is handled by timers; just swallow */ });
    document.addEventListener('visibilitychange', () => { if (!A.ctx) return; if (document.hidden) A.ctx.suspend(); else A.ctx.resume(); });
    window.addEventListener('resize', layout); window.addEventListener('orientationchange', () => setTimeout(layout, 200));
    // first gesture anywhere unlocks audio
    const unlock = () => { A.init(); A.resume(); if (A.ctx && !A.playing) A.play(0, 'menu'); window.removeEventListener('pointerdown', unlock); };
    window.addEventListener('pointerdown', unlock);
  }

  // ------------------------------------------------------------ rendering
  function drawGadgets() {
    const wt = WT();
    for (const z of world.vortex) {
      sctx.save(); sctx.translate(z.x, z.y);
      const g = sctx.createRadialGradient(0, 0, 4, 0, 0, z.r); g.addColorStop(0, 'rgba(20,0,40,.75)'); g.addColorStop(0.5, 'rgba(120,60,255,.28)'); g.addColorStop(1, 'rgba(120,60,255,0)');
      sctx.fillStyle = g; sctx.beginPath(); sctx.arc(0, 0, z.r, 0, TAU); sctx.fill();
      sctx.rotate(time * 1.6); sctx.strokeStyle = 'rgba(210,190,255,.8)'; sctx.lineWidth = 4; sctx.lineCap = 'round';
      for (let k = 0; k < 3; k++) { sctx.rotate(TAU / 3); sctx.beginPath(); for (let t = 0; t < 1; t += 0.05) { const a = t * 3.2, rr = 12 + t * 120; sctx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); } sctx.stroke(); }
      sctx.restore();
    }
    for (const p of world.portals) {
      [p.a, p.b].forEach((q, i) => {
        sctx.save(); sctx.translate(q.x, q.y);
        const col = i ? '#7fe9ff' : '#c79bff';
        const g = sctx.createRadialGradient(0, 0, 2, 0, 0, 34); g.addColorStop(0, '#05010c'); g.addColorStop(0.7, i ? '#0b2f55' : '#2c0b55'); g.addColorStop(1, col);
        sctx.fillStyle = g; sctx.beginPath(); sctx.arc(0, 0, 32, 0, TAU); sctx.fill();
        sctx.strokeStyle = col; sctx.lineWidth = 5; sctx.setLineDash([14, 9]); sctx.lineDashOffset = -time * 40 * (i ? -1 : 1); sctx.beginPath(); sctx.arc(0, 0, 38, 0, TAU); sctx.stroke(); sctx.setLineDash([]);
        sctx.strokeStyle = '#fff'; sctx.lineWidth = 2; sctx.beginPath(); sctx.arc(0, 0, 25 + Math.sin(time * 4 + i) * 3, 0, TAU); sctx.stroke();
        sctx.restore();
      });
    }
    for (const b of world.bumpers) {
      const pl = b.pulse || 0, rr = b.r + pl * 8;
      sctx.save(); sctx.translate(b.x, b.y);
      sctx.fillStyle = 'rgba(0,0,0,.28)'; sctx.beginPath(); sctx.ellipse(3, 8, rr + 4, rr * 0.7, 0, 0, TAU); sctx.fill();
      const g = sctx.createRadialGradient(-rr * 0.3, -rr * 0.3, 2, 0, 0, rr); g.addColorStop(0, '#fff7c0'); g.addColorStop(0.5, wt.rim[0]); g.addColorStop(1, wt.rim[1]);
      sctx.fillStyle = g; sctx.beginPath(); sctx.arc(0, 0, rr, 0, TAU); sctx.fill(); sctx.lineWidth = 4; sctx.strokeStyle = INK; sctx.stroke();
      sctx.fillStyle = pl > 0.2 ? '#fff' : wt.rimEdge; Art.star(sctx, 0, 0, rr * 0.5, pl > 0.2 ? '#fff' : '#ffffff');
      sctx.strokeStyle = 'rgba(255,255,255,' + (0.4 + pl * 0.6) + ')'; sctx.lineWidth = 3; sctx.beginPath(); sctx.arc(0, 0, rr + 7 + pl * 6, 0, TAU); sctx.stroke();
      sctx.restore();
    }
  }

  function segDist(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1;
    const t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0, 1);
    return Math.hypot(px - (ax + dx * t), py - (ay + dy * t));
  }
  function worryAlong(pv) {
    for (const f of world.fruits()) {
      let near = f === pv.hit;
      if (!near) for (let i = 0; i < pv.pts.length - 1; i++) { if (segDist(f.x, f.y, pv.pts[i].x, pv.pts[i].y, pv.pts[i + 1].x, pv.pts[i + 1].y) < f.r + 26) { near = true; break; } }
      if (near) { const v = vis(f); if (v.mood === 'idle') { v.mood = 'worry'; v.moodT = 0.15; } }
    }
  }
  function drawGuide(pv, col, width, dashed, pulse) {
    sctx.save(); sctx.lineCap = 'round'; sctx.lineJoin = 'round';
    sctx.strokeStyle = col; sctx.lineWidth = width; sctx.setLineDash(dashed ? [3, 16] : []); sctx.lineDashOffset = -time * 34;
    sctx.beginPath(); pv.pts.forEach((p, i) => i ? sctx.lineTo(p.x, p.y) : sctx.moveTo(p.x, p.y)); sctx.stroke();
    sctx.setLineDash([]);
    if (pv.hit) {
      sctx.globalAlpha = 0.55; sctx.fillStyle = col; sctx.beginPath(); sctx.arc(pv.x, pv.y, world.cue.r, 0, TAU); sctx.fill();
      sctx.globalAlpha = 1; sctx.lineWidth = 4; sctx.strokeStyle = col; sctx.beginPath(); sctx.arc(pv.hit.x, pv.hit.y, pv.hit.r + 8 + (pulse ? Math.sin(time * 8) * 3 : 0), 0, TAU); sctx.stroke();
    }
    sctx.restore();
  }
  function drawAim() {
    const c = world.cue;
    if (aim && aim.active && phase === 'aim' && aim.len > DEAD) {
      const dir = { x: Math.cos(aim.ang), y: Math.sin(aim.ang) };
      const pv = G.rayPreview(world, dir.x, dir.y); worryAlong(pv);
      drawGuide(pv, 'rgba(255,255,255,.95)', 7, true, true);
      // slingshot band toward the pull
      const pull = Math.min(aim.len, MAXPULL + DEAD);
      const ex = c.x - dir.x * pull * 0.8, ey = c.y - dir.y * pull * 0.8;
      const hue = 120 - aim.pow * 120;
      sctx.save(); sctx.lineCap = 'round';
      sctx.strokeStyle = 'rgba(0,0,0,.25)'; sctx.lineWidth = 16; sctx.beginPath(); sctx.moveTo(c.x + 3, c.y + 4); sctx.lineTo(ex + 3, ey + 4); sctx.stroke();
      sctx.strokeStyle = `hsl(${hue},95%,60%)`; sctx.lineWidth = 12; sctx.beginPath(); sctx.moveTo(c.x, c.y); sctx.lineTo(ex, ey); sctx.stroke();
      sctx.strokeStyle = 'rgba(255,255,255,.7)'; sctx.lineWidth = 4; sctx.beginPath(); sctx.moveTo(c.x, c.y); sctx.lineTo(ex, ey); sctx.stroke();
      sctx.fillStyle = `hsl(${hue},95%,60%)`; sctx.strokeStyle = INK; sctx.lineWidth = 4; sctx.beginPath(); sctx.arc(ex, ey, 15, 0, TAU); sctx.fill(); sctx.stroke();
      sctx.lineWidth = 8; sctx.strokeStyle = `hsl(${hue},95%,60%)`; sctx.beginPath(); sctx.arc(c.x, c.y, c.r + 14, -Math.PI / 2, -Math.PI / 2 + TAU * Math.max(0.03, aim.pow)); sctx.stroke();
      sctx.restore();
    } else if (hint && phase === 'aim') {
      const pv = G.rayPreview(world, Math.cos(hint.angle), Math.sin(hint.angle));
      drawGuide(pv, '#ffe35a', 8, true, true);
      sctx.save(); sctx.font = '900 30px "Trebuchet MS",Verdana,sans-serif'; sctx.textAlign = 'center'; sctx.lineWidth = 8; sctx.strokeStyle = INK; sctx.lineJoin = 'round';
      const tx = clamp(c.x + Math.cos(hint.angle) * 120, 90, W - 90), ty = clamp(c.y + Math.sin(hint.angle) * 120, 90, H - 90);
      const label = hint.left === 0 ? 'CLEARS THE TABLE!' : '~' + hint.pops + ' POPS';
      sctx.strokeText(label, tx, ty); sctx.fillStyle = '#ffe35a'; sctx.fillText(label, tx, ty);
      sctx.fillStyle = '#fff'; sctx.font = '700 20px "Trebuchet MS",Verdana,sans-serif'; sctx.strokeText('pull back opposite', tx, ty + 28); sctx.fillText('pull back opposite', tx, ty + 28);
      sctx.restore();
    }
    if (solver) {  // "thinking" shimmer around the lemon
      sctx.save(); sctx.strokeStyle = '#ffe35a'; sctx.lineWidth = 5; sctx.setLineDash([10, 10]); sctx.lineDashOffset = -time * 80;
      sctx.beginPath(); sctx.arc(c.x, c.y, c.r + 22, 0, TAU); sctx.stroke(); sctx.restore();
    }
  }

  function drawBody(b) {
    const v = vis(b), d = G.FRUITS[b.type];
    sctx.save(); sctx.translate(b.x, b.y);
    const primed = b.fuse >= 0;
    if (primed) sctx.translate(Math.sin(time * 90 + b.id) * 2.2, Math.cos(time * 77 + b.id) * 1.8);
    if (b.gold) Art.goldAura(sctx, b.r, time + b.id);
    const br = 1 + 0.022 * Math.sin(time * 2.4 + v.phase);
    let sx = br, sy = 2 - br;
    if (primed) { const pu = 1 + 0.06 * Math.sin(time * 40); sx *= pu; sy *= pu; }
    sctx.scale(sx, sy);
    if (v.squash > 0.01) { sctx.rotate(v.sa); sctx.scale(1 - v.squash, 1 + v.squash * 0.7); sctx.rotate(-v.sa); }
    const sp = Math.hypot(b.vx, b.vy);
    if (sp > 220) { const a = Math.atan2(b.vy, b.vx), st = Math.min(0.2, sp / 8000); sctx.rotate(a); sctx.scale(1 + st, 1 - st * 0.7); sctx.rotate(-a); }
    Art.body(sctx, b.type, b.r, b);
    if (primed) {   // angry red pulse overlay + fuse sparkle
      sctx.globalAlpha = 0.35 + 0.25 * Math.sin(time * 36); sctx.fillStyle = '#ff2b2b'; sctx.beginPath(); sctx.arc(0, 0, b.r * 1.02, 0, TAU); sctx.fill(); sctx.globalAlpha = 1;
      Art.star(sctx, Math.sin(time * 30) * 4, -b.r * 1.15, 8 + Math.sin(time * 50) * 3, '#fff3a0');
    }
    if (b.type === 'banana' && !primed) { // faint beam hint
      sctx.save(); sctx.rotate(b.ang0); sctx.strokeStyle = 'rgba(255,245,150,.35)'; sctx.lineWidth = 5; sctx.setLineDash([4, 14]); sctx.lineDashOffset = -time * 20;
      sctx.beginPath(); sctx.moveTo(-d.beam, 0); sctx.lineTo(d.beam, 0); sctx.stroke(); sctx.restore();
    }
    const fv = { look: v.look, mood: v.mood, blink: v.blink, t: v.t, moodT: v.moodT, smirk: v.smirk };
    if (b.type !== 'pit') Art.face(sctx, b.r, fv, b.type);
    sctx.restore();
    if (b.type === 'boss' || (b.type === 'melon' && b.hp < 2) || (b.type === 'pineapple' && b.hp < 2)) {
      if (b.type === 'boss') {
        const w = 120, x0 = b.x - w / 2, y0 = b.y - b.r - 44;
        sctx.fillStyle = INK; sctx.fillRect(x0 - 3, y0 - 3, w + 6, 16); sctx.fillStyle = '#ff3d7a'; sctx.fillRect(x0, y0, w * clamp(b.hp / b.maxHp, 0, 1), 10);
        sctx.fillStyle = 'rgba(255,255,255,.4)'; sctx.fillRect(x0, y0, w * clamp(b.hp / b.maxHp, 0, 1), 3);
      }
    }
  }

  function drawLemonTrail() {
    const c = world.cue;
    if (!c.alive) { trail.length = 0; return; }
    const sp = Math.hypot(c.vx, c.vy);
    if (sp > 260) { trail.push({ x: c.x, y: c.y, a: 1 }); if (trail.length > 12) trail.shift(); } else if (trail.length) trail.shift();
    for (let i = 0; i < trail.length; i++) {
      const t = trail[i], k = (i + 1) / trail.length;
      sctx.globalAlpha = 0.28 * k; sctx.fillStyle = '#fff17a'; sctx.beginPath(); sctx.arc(t.x, t.y, c.r * (0.45 + 0.5 * k), 0, TAU); sctx.fill();
    }
    sctx.globalAlpha = 1;
  }

  function render() {
    const sh = FX.shake, ox = sh ? (Math.random() - 0.5) * sh * 1.7 : 0, oy = sh ? (Math.random() - 0.5) * sh * 1.7 : 0;
    sctx.setTransform(pxs, 0, 0, pxs, 0, 0);
    sctx.fillStyle = WT().bg[0]; sctx.fillRect(0, 0, W, H);
    sctx.save(); sctx.translate(ox, oy);
    if (sh > 12) { const z = 1 + sh * 0.0016; sctx.translate(W / 2, H / 2); sctx.scale(z, z); sctx.translate(-W / 2, -H / 2); }
    sctx.drawImage(tableCv, 0, 0, W, H);
    FX.drawLow(sctx);
    if (world) {
      drawGadgets();
      drawAim();
      drawLemonTrail();
      for (const b of world.bodies) if (b.alive) { sctx.fillStyle = 'rgba(0,0,0,.26)'; sctx.beginPath(); sctx.ellipse(b.x + 3, b.y + b.r * 0.32, b.r * 0.95, b.r * 0.62, 0, 0, TAU); sctx.fill(); }
      const ordered = world.bodies.filter(b => b.alive).sort((a, b) => a.y - b.y);
      for (const b of ordered) drawBody(b);
    }
    FX.draw(sctx);
    sctx.restore();
    // post-process
    const rip = FX.ripples.map(r => ({ x: r.x, y: r.y, r: r.age * 0.7, s: Math.min(0.8, r.s) * Math.max(0, 1 - r.age / 0.9) }));
    const params = { time, aberr: FX.aberr + FX.shake * 0.00022, sat: 0.1 + Math.min(0.3, chainN * 0.03) + rainbow * 0.1, rainbow: Math.min(1, rainbow), flash: FX.flash * 0.35, ripples: rip, vig: 0.55 };
    if (useGL && G.GL.ok) {
      try { G.GL.render(scene, params); } catch (er) { useGL = false; console.warn(er); }
    } else if (dctx) dctx.drawImage(scene, 0, 0);
  }

  // ------------------------------------------------------------ main loop
  let last = performance.now();
  function frame(ts) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (ts - last) / 1000); last = ts;
    if (paused || document.hidden) return;
    time += dt;
    if (rainbow > 0) rainbow = Math.max(0, rainbow - dt * 0.6);
    if (levelFlash > 0) levelFlash -= dt;
    if (world) {
      if (FX.hitstop > 0) FX.hitstop -= dt;
      else {
        let ts2 = fast ? 2.4 : 1;
        if (FX.slow > 0) { ts2 *= 0.3; FX.slow -= dt; }
        acc += dt * ts2; let steps = 0;
        while (acc >= G.DT && steps < 14) { world.step(); acc -= G.DT; steps++; if (world.events.length) handleEvents(); }
        if (steps >= 14) acc = 0;
      }
      if (phase === 'roll') {
        rollT += dt;
        if (rollT > 14) { for (const b of world.bodies) { b.vx = b.vy = 0; b.fuse = -1; } }
        if (rollT > 0.3 && world.isSettled()) { fast = false; resolveShot(); }
      }
      if (solver) { solver.run(7); if (solver.done) { hint = solver.best; solver = null; updateHud(); } }
      if (phase === 'title') {   // attract mode: the lemon plays itself
        const at = attract; at.t -= dt;
        if (at.stage === 'wait' && at.t <= 0) { solver = G.makeSolver(world); at.stage = 'think'; }
        else if (at.stage === 'think' && hint) { world.shoot(hint.angle, hint.power); hint = null; at.stage = 'roll'; rollT = 0; }
        else if (at.stage === 'roll') { rollT += dt; if ((rollT > 0.5 && world.isSettled()) || rollT > 9) { at.stage = 'rest'; at.t = 1.7; A.setIntensity(1); } }
        else if (at.stage === 'rest' && at.t <= 0) { if (world.fruitCount() > 0 && world.shots < 3) { at.stage = 'wait'; at.t = 0.3; } else startAttract(); }
      }
      FX.update(dt);
      updateFaces(dt);
      if (chainShow > 0) { chainShow -= dt; }
      if (frameCount++ % 6 === 0) updateHud();
      const cb = $('combo');
      if (chainN >= 3 && phase === 'roll') { cb.textContent = 'x' + chainN; cb.classList.add('on'); } else cb.classList.remove('on');
    } else FX.update(dt);
    render();
  }
  let frameCount = 0;

  // ------------------------------------------------------------ boot
  function boot() {
    Gem.make($('gemBox'), 'hud'); Gem.make($('titleGem'), 'big'); Gem.make($('clearGem'), 'big'); Gem.make($('storyGemSlot'), 'big');
    Gem.attach($('bubble'), $('bubbleText'));
    wireUI(); syncSnd();
    layout();
    openTitle();
    requestAnimationFrame(frame);
    // tiny debug/test hook
    window.__game = { get world() { return world; }, get phase() { return phase; }, startLevel, shoot, doZest, doMega, doHint, get par() { return par; }, FX, Save, setPaused(p) { paused = p; } };
  }
  window.addEventListener('load', () => { boot(); });
  // keep bubble docked whenever a level starts
  const obs = new MutationObserver(() => { if (document.body.dataset.phase === 'aim' && $('bubble').parentElement.id !== 'bubbleCol') dockBubble(); });
  obs.observe(document.body, { attributes: true, attributeFilter: ['data-phase'] });
})();
