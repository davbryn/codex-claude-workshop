/* Level generator: every level number maps to one deterministic layout (so levels are endless). */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};
  const TB = G.TABLE;

  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  G.rng = rng;

  G.WORLDS = [
    { name: 'The Lounge', tag: 'Where it all began', felt: ['#3ee6ac', '#13b47b'], rim: ['#ffd1f3', '#c46bd0'], rimEdge: '#7b2d8e', bg: ['#2b0f55', '#0c1a4d'], line: 'rgba(255,255,255,.16)', song: 0 },
    { name: 'Bumper Bar', tag: 'Pinball but juicier', felt: ['#8c78ff', '#4b33d4'], rim: ['#ffe29a', '#f09a2e'], rimEdge: '#9a5410', bg: ['#1c0a3d', '#40124e'], line: 'rgba(255,255,255,.14)', song: 1 },
    { name: 'Portal Patio', tag: 'Mind the wormholes', felt: ['#2fd0d8', '#0c8fa8'], rim: ['#ffc2a8', '#ee6b5b'], rimEdge: '#8d2a2a', bg: ['#07304a', '#2a0f4d'], line: 'rgba(255,255,255,.14)', song: 2 },
    { name: 'Jelly Lagoon', tag: 'Slippery. Wobbly. Doomed.', felt: ['#c25bd6', '#7d2aa6'], rim: ['#c9fbff', '#4fb8d6'], rimEdge: '#1d6f8e', bg: ['#0a1a3f', '#0b4f63'], line: 'rgba(255,255,255,.15)', song: 3 }
  ];

  const ORDER = ['apple', 'orange', 'cherry', 'banana', 'chili', 'pineapple', 'blueberry', 'melon'];
  G.ORDER = ORDER;
  // the level on which each fruit makes its debut
  G.DEBUT = { apple: 1, orange: 2, cherry: 3, banana: 4, chili: 5, pineapple: 7, blueberry: 9, melon: 11 };
  function allowed(n) {
    return ORDER.filter(t => n >= G.DEBUT[t]);
  }

  const X0 = TB.L + 62, X1 = TB.R - 62, Y0 = TB.T + 120, Y1 = TB.B - 250;

  // ---- patterns: return points around (0,0)
  const PAT = {
    rack(n, s) { const p = []; let row = 0; while (p.length < n) { for (let j = 0; j <= row && p.length < n; j++) p.push([(j - row / 2) * s, row * s * 0.88]); row++; } return p; },
    ring(n, s) { const r = Math.max(s * 0.9, n * s / (Math.PI * 2)); return Array.from({ length: n }, (_, i) => [Math.cos(i / n * 6.283) * r, Math.sin(i / n * 6.283) * r]); },
    line(n, s) { return Array.from({ length: n }, (_, i) => [(i - (n - 1) / 2) * s, 0]); },
    vee(n, s) { return Array.from({ length: n }, (_, i) => { const k = i - (n - 1) / 2; return [k * s * 0.8, Math.abs(k) * s * 0.7]; }); },
    cross(n, s) { const p = [[0, 0]]; let k = 1; while (p.length < n) { p.push([k * s, 0]); if (p.length < n) p.push([-k * s, 0]); if (p.length < n) p.push([0, k * s]); if (p.length < n) p.push([0, -k * s]); k++; } return p; },
    grid(n, s) { const c = Math.ceil(Math.sqrt(n)); return Array.from({ length: n }, (_, i) => [(i % c - (c - 1) / 2) * s, (Math.floor(i / c) - (c - 1) / 2) * s]); },
    spiral(n, s) { return Array.from({ length: n }, (_, i) => { const a = i * 2.4, r = s * 0.55 * Math.sqrt(i + 0.6) * 1.15; return [Math.cos(a) * r, Math.sin(a) * r]; }); },
    wave(n, s) { return Array.from({ length: n }, (_, i) => [(i - (n - 1) / 2) * s * 0.9, Math.sin(i * 1.1) * s * 0.7]); },
    diamond(n, s) { const p = [[0, 0]]; let k = 1; while (p.length < n) { for (const [a, b] of [[k, 0], [-k, 0], [0, k], [0, -k]]) if (p.length < n) p.push([a * s * 0.8, b * s * 0.8]); k++; } return p; }
  };
  const PAT_NAMES = Object.keys(PAT);

  G.makeLevel = function (n) {
    const rnd = rng(n * 7919 + 101);
    const wi = Math.floor((n - 1) / 6) % 4;
    const cycle = Math.floor((n - 1) / 24);
    const boss = n % 6 === 0;
    const lvl = { n, world: wi, boss, fruits: [], bumpers: [], blocks: [], portals: [], zones: [], vortex: [], lemon: { x: 360, y: 860 } };
    const used = [{ x: 360, y: 860, r: 120 }];
    const nearPocket = (x, y, m) => TB.POCKETS.some(p => Math.hypot(p.x - x, p.y - y) < m);
    const free = (x, y, r) => used.every(u => Math.hypot(u.x - x, u.y - y) >= u.r + r);
    function spot(r, tries) {
      for (let i = 0; i < (tries || 80); i++) {
        const x = X0 + rnd() * (X1 - X0), y = Y0 + rnd() * (Y1 - Y0 + 40);
        if (!nearPocket(x, y, 110) && free(x, y, r)) return { x, y };
      }
      return null;
    }

    // --- table gadgets per world (later cycles mix them in)
    const nb = (wi === 1 ? 2 + Math.floor(n / 9) : (cycle > 0 || wi === 2 ? 1 + cycle : 0));
    for (let i = 0; i < Math.min(5, nb); i++) { const s = spot(60); if (s) { lvl.bumpers.push({ x: s.x, y: s.y, r: 26 }); used.push({ x: s.x, y: s.y, r: 52 }); } }
    if (wi === 1) {
      const nbl = 1 + (n > 12 ? 1 : 0);
      for (let i = 0; i < nbl; i++) { const vert = rnd() < 0.4, w = vert ? 28 : 130, h = vert ? 130 : 28; const s = spot(86); if (s) { lvl.blocks.push({ x: s.x, y: s.y, w, h }); used.push({ x: s.x, y: s.y, r: 80 }); } }
    }
    if (wi === 2 || (cycle > 0 && wi === 0)) {
      const np = n > 18 ? 2 : 1;
      for (let i = 0; i < np; i++) {
        const a = spot(70), bb = a && spot(70);
        if (a && bb) {
          if (Math.hypot(a.x - bb.x, a.y - bb.y) < 260) { bb.x = TB.W - a.x; bb.y = Math.min(Y1, TB.H - a.y - 200); }
          lvl.portals.push({ a: { x: a.x, y: a.y }, b: { x: bb.x, y: bb.y }, hue: i * 140 });
          used.push({ x: a.x, y: a.y, r: 64 }, { x: bb.x, y: bb.y, r: 64 });
        }
      }
    }
    if (wi === 3 || (cycle > 0 && wi === 1)) {
      const ice = spot(120);
      if (ice) { lvl.zones.push({ kind: 'ice', x: ice.x, y: ice.y, w: 250, h: 190, k: 0.08, c: 0 }); used.push({ x: ice.x, y: ice.y, r: 100 }); }
      const jel = spot(110);
      if (jel) { lvl.zones.push({ kind: 'jelly', x: jel.x, y: jel.y, w: 200, h: 170, k: 5.5, c: 260 }); used.push({ x: jel.x, y: jel.y, r: 90 }); }
      if (n > 20 || wi === 3) { const v = spot(130); if (v) { lvl.vortex.push({ x: v.x, y: v.y, r: 190, s: 330 }); used.push({ x: v.x, y: v.y, r: 70 }); } }
    }
    // pull gadget-zone placements into 'used' so fruit is spaced from them
    const types = allowed(n);
    const newest = types[types.length - 1];
    const sp = Math.min(104, 82 + n * 0.9);
    let count = boss ? 7 + Math.min(5, Math.floor(n / 12)) : Math.min(18, 5 + Math.floor(n * 0.55));
    if (n === 1) count = 5;
    lvl.count = count;

    const pts = [];
    const place = (px, py) => {
      if (px < X0 || px > X1 || py < Y0 || py > Y1) return false;
      if (nearPocket(px, py, 100)) return false;
      if (!lvl.bumpers.every(b => Math.hypot(b.x - px, b.y - py) > b.r + 52)) return false;
      if (!lvl.blocks.every(b => Math.abs(b.x - px) > b.w / 2 + 50 || Math.abs(b.y - py) > b.h / 2 + 50)) return false;
      if (!lvl.portals.every(p => Math.hypot(p.a.x - px, p.a.y - py) > 70 && Math.hypot(p.b.x - px, p.b.y - py) > 70)) return false;
      if (Math.hypot(px - lvl.lemon.x, py - lvl.lemon.y) < 190) return false;
      if (lvl.vortex.some(v => Math.hypot(v.x - px, v.y - py) < 60)) return false;
      if (pts.some(q => Math.hypot(q[0] - px, q[1] - py) < 74)) return false;
      return true;
    };
    const groups = boss ? 1 : (n < 3 ? 1 : Math.min(6, 1 + Math.floor((n + 1) / 4)));
    if (boss) {
      lvl.fruits.push({ type: 'boss', x: 360, y: 330 });
      pts.push([360, 330]);
      const m = count - 1;
      for (let i = 0; i < m; i++) {
        const a = -Math.PI / 2 + (i + 0.5) / m * Math.PI * 2 + 0.3, r = 205 + (i % 2) * 30;
        const px = 360 + Math.cos(a) * r, py = 345 + Math.sin(a) * r * 0.92;
        if (place(px, py)) pts.push([px, py]); else { const s = spot(40); if (s) pts.push([s.x, s.y]); }
      }
      pts.shift();
    } else {
      let remaining = count;
      for (let g = 0; g < groups; g++) {
        const gn = g === groups - 1 ? remaining : Math.max(2, Math.round(remaining / (groups - g)));
        remaining -= gn;
        let placed = false;
        for (let tries = 0; tries < 160 && !placed; tries++) {
          const gap = n < 3 ? 0 : Math.max(125, 215 - tries * 0.55);
          const pat = PAT[PAT_NAMES[Math.floor(rnd() * PAT_NAMES.length)]];
          const rel = pat(gn, sp * (0.9 + rnd() * 0.25));
          const cx = X0 + 40 + rnd() * (X1 - X0 - 80), cy = Y0 + 20 + rnd() * (Y1 - Y0 - 40);
          const cand = rel.map(p => [cx + p[0], cy + p[1]]);
          const tmp = [];
          let ok = true;
          for (const c of cand) { if (!place(c[0], c[1]) || tmp.some(q => Math.hypot(q[0] - c[0], q[1] - c[1]) < 74) || pts.some(q => Math.hypot(q[0] - c[0], q[1] - c[1]) < gap)) { ok = false; break; } tmp.push(c); }
          if (ok) { pts.push(...cand); placed = true; }
        }
        if (!placed) {   // fallback: scatter one by one
          for (let i = 0; i < gn; i++) {
            for (let t = 0; t < 120; t++) {
              const px = X0 + rnd() * (X1 - X0), py = Y0 + rnd() * (Y1 - Y0);
              if (place(px, py) && (pts.length === 0 || pts.some(q => Math.hypot(q[0] - px, q[1] - py) < sp * 1.6))) { pts.push([px, py]); break; }
            }
          }
        }
      }
    }
    // assign fruit types; make sure the newest one is shown off
    const typed = pts.map((p, i) => {
      let t = types[Math.floor(rnd() * types.length)];
      if (n === 1) t = 'apple';
      return { type: t, x: Math.round(p[0]), y: Math.round(p[1]) };
    });
    if (n >= 2 && newest !== 'apple') for (let i = 0; i < Math.min(2, typed.length); i++) if (n === G.DEBUT[newest] || rnd() < 0.5) typed[i].type = newest;
    // bananas aim their beam at a neighbour (usually), so they matter
    for (const f of typed) {
      if (f.type === 'banana') {
        const others = typed.filter(o => o !== f).sort((a, b) => Math.hypot(a.x - f.x, a.y - f.y) - Math.hypot(b.x - f.x, b.y - f.y));
        f.ang = others.length && rnd() < 0.7 ? Math.atan2(others[0].y - f.y, others[0].x - f.x) : Math.floor(rnd() * 8) * Math.PI / 4 + 0.4;
      }
    }
    if (typed.length > 2 && (n >= 3) && (n % 2 === 1 || rnd() < 0.4)) typed[Math.floor(rnd() * typed.length)].gold = true;
    lvl.fruits.push(...typed);
    lvl.count = lvl.fruits.length;
    lvl.par = G.parFor(n, lvl);
    lvl.name = G.WORLDS[wi].name;
    return lvl;
  };

  // par = what the built-in solver needs, as measured by tools/verify.js (falls back to a formula)
  G.PAR = {};
  G.parFor = function (n, lvl) {
    if (G.PAR[n]) return G.PAR[n];
    const per = Math.max(1.8, 3.1 - n * 0.03);
    return Math.max(2, Math.ceil(lvl.count / per) + (lvl.boss ? 2 : 0));
  };
})(typeof window !== 'undefined' ? window : globalThis);
