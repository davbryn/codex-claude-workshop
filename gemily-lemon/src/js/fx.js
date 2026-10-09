/* Visual juice: particles, juice stains that stay on the felt, flying googly eyes, confetti, floating text, shake. */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};
  const FX = G.FX = { parts: [], shake: 0, flash: 0, aberr: 0, ripples: [], slow: 0, hitstop: 0, stainCv: null };
  const TAU = Math.PI * 2;
  const R = (a, b) => a + Math.random() * (b - a);
  const INK = '#2a0f3a';
  const CONF = ['#ff3d7a', '#ffd23c', '#3de6a8', '#4db8ff', '#b46bff', '#ff8a3c', '#ffffff'];

  const JUICE = {
    apple: ['#ff3b5c', '#d1203f', '#ff8fa0'], orange: ['#ff9f1c', '#f2780c', '#ffd27a'], cherry: ['#e0245e', '#8a0c37', '#ff7aa5'],
    banana: ['#ffe94d', '#f2c10a', '#fff6a8'], chili: ['#ff4d2e', '#ff9a1f', '#ffd54a'], pineapple: ['#ffd84d', '#f5a300', '#fff1a0'],
    blueberry: ['#6b4dff', '#3b2bb5', '#a99bff'], melon: ['#ff4f6e', '#58d66b', '#ff9aae'], boss: ['#ff4f6e', '#58d66b', '#ffd23c'],
    lemon: ['#fff06a', '#f5c400', '#fffbb0']
  };
  FX.juice = JUICE;
  const QUIPS = ['Mama!', 'Not the face!', 'Tell my seeds...', 'Peel good!', 'AAAAH!', 'I was ripe!', 'Seed you later!', 'Oh nooo', 'Zest in peace', 'Squish!', 'Why meee', 'I regret nothing', 'Berry sorry!', 'Juicy!!', 'Pulp fiction'];
  FX.quip = () => QUIPS[Math.floor(Math.random() * QUIPS.length)];

  FX.init = function (W, H, scale) {
    FX.W = W; FX.H = H; FX.scale = scale;
    const c = FX.stainCv = document.createElement('canvas');
    c.width = Math.round(W * scale); c.height = Math.round(H * scale);
    FX.sctx = c.getContext('2d');
    FX.sctx.scale(scale, scale);
    FX.reset();
  };
  FX.resize = function (scale) {
    // keep stains when the scene is resized
    const old = FX.stainCv, c = document.createElement('canvas');
    c.width = Math.round(FX.W * scale); c.height = Math.round(FX.H * scale);
    const x = c.getContext('2d'); x.drawImage(old, 0, 0, c.width, c.height); x.scale(scale, scale);
    FX.stainCv = c; FX.sctx = x; FX.scale = scale;
  };
  FX.reset = function () {
    FX.parts.length = 0; FX.shake = 0; FX.flash = 0; FX.ripples.length = 0; FX.slow = 0; FX.hitstop = 0;
    FX.sctx.clearRect(0, 0, FX.W, FX.H);
  };

  FX.stain = function (x, y, col, size) {
    const c = FX.sctx; c.save(); c.globalAlpha = 0.5; c.fillStyle = col;
    c.beginPath();
    const n = 14, r0 = size;
    for (let i = 0; i <= n; i++) { const a = i / n * TAU, r = r0 * (0.75 + Math.random() * 0.5); c.lineTo(x + Math.cos(a) * r, y + Math.sin(a) * r); }
    c.closePath(); c.fill();
    const drops = 6 + Math.floor(size / 6);
    for (let i = 0; i < drops; i++) {
      const a = Math.random() * TAU, d = size * R(0.9, 2.2), s = R(2, size * 0.28);
      c.beginPath(); c.arc(x + Math.cos(a) * d, y + Math.sin(a) * d, s, 0, TAU); c.fill();
      c.lineWidth = s * 0.9; c.strokeStyle = col; c.globalAlpha = 0.35;
      c.beginPath(); c.moveTo(x + Math.cos(a) * size * 0.6, y + Math.sin(a) * size * 0.6); c.lineTo(x + Math.cos(a) * d, y + Math.sin(a) * d); c.stroke(); c.globalAlpha = 0.5;
    }
    c.restore();
  };

  function add(p) { if (FX.parts.length < 900) FX.parts.push(p); return p; }

  FX.drops = function (x, y, type, n, power) {
    const pal = JUICE[type] || JUICE.apple;
    for (let i = 0; i < n; i++) {
      const a = Math.random() * TAU, s = R(0.25, 1) * power;
      add({ k: 'drop', x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: R(0.35, 0.8), max: 0.8, size: R(3, 10), col: pal[i % 3], stain: Math.random() < 0.35 });
    }
  };
  FX.chunks = function (type, x, y, n, power) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * TAU, s = R(0.3, 1) * power;
      add({ k: 'chunk', type, x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, rot: Math.random() * TAU, vr: R(-12, 12), life: R(0.7, 1.4), max: 1.4, size: R(7, 14), pick: i % 3 });
    }
  };
  FX.confetti = function (x, y, n, power, spread) {
    for (let i = 0; i < n; i++) {
      const a = spread != null ? -Math.PI / 2 + R(-spread, spread) : Math.random() * TAU, s = R(0.2, 1) * power;
      add({ k: 'conf', x, y, z: 0, vx: Math.cos(a) * s, vy: Math.sin(a) * s, rot: Math.random() * TAU, vr: R(-10, 10), flip: Math.random() * TAU,
        life: R(1.6, 3.2), max: 3.2, w: R(7, 13), h: R(4, 8), col: CONF[Math.floor(Math.random() * CONF.length)] });
    }
  };
  FX.rain = function (n) {
    for (let i = 0; i < n; i++) add({ k: 'conf', x: R(0, FX.W), y: R(-80, -10), vx: R(-40, 40), vy: R(60, 260), rot: Math.random() * TAU, vr: R(-8, 8), flip: Math.random() * TAU, life: R(2.2, 4), max: 4, w: R(8, 14), h: R(5, 9), col: CONF[Math.floor(Math.random() * CONF.length)], grav: 60 });
  };
  FX.eyes = function (x, y, r) {
    for (let k = 0; k < 2; k++) {
      const a = Math.random() * TAU, s = R(120, 360);
      add({ k: 'eye', x, y, z: 14, vz: R(420, 760), vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 2.2, max: 2.2, size: Math.max(7, r * 0.3), pa: Math.random() * TAU, bounces: 0 });
    }
  };
  FX.ring = function (x, y, r1, col, w, life) { add({ k: 'ring', x, y, r1, col: col || '#fff', w: w || 8, life: life || 0.45, max: life || 0.45 }); };
  FX.flashCircle = function (x, y, r, col) { add({ k: 'flash', x, y, r, col: col || '#fff', life: 0.22, max: 0.22 }); };
  FX.sparks = function (x, y, n, power, col) {
    for (let i = 0; i < n; i++) { const a = Math.random() * TAU, s = R(0.4, 1) * power; add({ k: 'spark', x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: R(0.2, 0.5), max: 0.5, col: col || '#fff7b0', w: R(2, 4) }); }
  };
  FX.beam = function (x, y, ang, len) { add({ k: 'beam', x, y, ang, len, life: 0.45, max: 0.45 }); };
  FX.text = function (x, y, str, o) {
    o = o || {};
    x = Math.max(80, Math.min(FX.W - 80, x)); y = Math.max(70, y);
    add({ k: 'text', x, y, str, size: o.size || 44, col: o.col || '#fff', life: o.life || 1.0, max: o.life || 1.0, vy: o.vy == null ? -60 : o.vy, rot: o.rot == null ? R(-0.18, 0.18) : o.rot, stroke: o.stroke || INK });
  };
  FX.bubble = function (x, y, str) { // tiny dying words
    x = Math.max(70, Math.min(FX.W - 70, x));
    add({ k: 'quip', x, y, str, life: 1.2, max: 1.2 });
  };
  FX.ripple = function (x, y, str) {
    FX.ripples.push({ x: x / FX.W, y: 1 - y / FX.H, age: 0, s: str || 1 });
    if (FX.ripples.length > 4) FX.ripples.shift();
  };
  FX.kick = function (shake, flash, aberr) {
    FX.shake = Math.min(34, Math.max(FX.shake, shake));
    FX.flash = Math.max(FX.flash, flash || 0); FX.aberr = Math.max(FX.aberr, aberr || 0);
  };

  // a proper fruit explosion (everything the player sees when something pops)
  FX.explode = function (e) {
    const t = e.type, x = e.x, y = e.y, d = G.FRUITS[t], pal = JUICE[t] || JUICE.apple;
    const big = t === 'boss' ? 3 : (t === 'melon' || t === 'pineapple') ? 1.5 : (t === 'blueberry' || t === 'cherry') ? 0.7 : 1;
    FX.drops(x, y, t, Math.round(16 * big), 380 * big);
    FX.chunks(t, x, y, Math.round(6 * big), 420 * big);
    FX.eyes(x, y, d.r);
    FX.ring(x, y, d.blast * 0.85, pal[2], 10 * big, 0.5);
    FX.ring(x, y, d.blast * 0.5, '#fff', 5, 0.3);
    FX.flashCircle(x, y, d.r * 2.2 * big, '#fff');
    FX.sparks(x, y, 8, 520, pal[2]);
    FX.stain(x, y, pal[0], d.r * 0.9 * (big > 1 ? 1.6 : 1));
    if (e.depth >= 3 || e.gold || big > 1) FX.confetti(x, y, 10 + Math.min(30, e.depth * 4), 560, null);
    if (t === 'chili') { FX.sparks(x, y, 18, 700, '#ff9a1f'); FX.kick(0, 0.18, 0.004); }
    if (e.gold) { FX.sparks(x, y, 30, 800, '#ffe35a'); FX.confetti(x, y, 50, 700); FX.kick(22, 0.35, 0.008); }
    const s = 6 + big * 5 + Math.min(10, e.depth * 1.5) + (e.pocket ? 4 : 0);
    FX.kick(s, 0.05 + big * 0.03, 0.002 + 0.0012 * Math.min(8, e.depth));
    FX.ripple(x, y, 0.6 + 0.35 * big + Math.min(0.5, e.depth * 0.08));
    FX.hitstop = Math.max(FX.hitstop, t === 'boss' ? 0.22 : 0.035 + 0.01 * Math.min(4, e.depth));
    const words = { apple: 'SPLAT!', orange: 'ZEST!', cherry: 'PLOP!', banana: 'SLIP!', chili: 'SPICY!', pineapple: 'KABOOM!', blueberry: 'PLIP!', melon: 'SMASH!', boss: 'MEGA-MELON DOWN!' };
    if (e.depth < 1 || Math.random() < 0.35) FX.text(x, y - 30, words[t] || 'POP!', { size: t === 'boss' ? 56 : 38 + Math.min(14, e.depth * 3), col: pal[2], life: 0.8 });
    if (Math.random() < 0.55) FX.bubble(x + R(-20, 20), y - d.r - 14, FX.quip());
  };

  FX.update = function (dt) {
    FX.shake *= Math.pow(0.0009, dt); if (FX.shake < 0.2) FX.shake = 0;
    FX.flash = Math.max(0, FX.flash - dt * 1.8); FX.aberr = Math.max(0, FX.aberr - dt * 0.03);
    for (const r of FX.ripples) r.age += dt;
    FX.ripples = FX.ripples.filter(r => r.age < 0.9);
    const ps = FX.parts;
    for (let i = ps.length - 1; i >= 0; i--) {
      const p = ps[i];
      p.life -= dt;
      if (p.life <= 0) {
        if (p.k === 'drop' && p.stain) FX.stain(p.x, p.y, p.col, p.size * 0.5);
        ps.splice(i, 1); continue;
      }
      switch (p.k) {
        case 'drop': case 'chunk': case 'spark': {
          const dr = Math.pow(p.k === 'spark' ? 0.02 : 0.04, dt); p.vx *= dr; p.vy *= dr; p.x += p.vx * dt; p.y += p.vy * dt;
          if (p.rot != null) p.rot += p.vr * dt; break;
        }
        case 'conf': {
          p.vx *= Math.pow(0.35, dt); p.vy = p.vy * Math.pow(0.5, dt) + (p.grav == null ? 380 : p.grav) * dt;
          p.x += p.vx * dt + Math.sin(p.flip) * 18 * dt; p.y += p.vy * dt; p.rot += p.vr * dt; p.flip += dt * 9; break;
        }
        case 'eye': {
          p.vz -= 1900 * dt; p.z += p.vz * dt; p.x += p.vx * dt; p.y += p.vy * dt;
          p.vx *= Math.pow(0.4, dt); p.vy *= Math.pow(0.4, dt);
          if (p.z < 0) { p.z = 0; if (p.vz < -120 && p.bounces < 4) { p.vz = -p.vz * 0.5; p.bounces++; p.pa += 2; } else p.vz = 0; }
          break;
        }
        case 'text': p.y += p.vy * dt; p.vy *= Math.pow(0.2, dt); break;
        case 'quip': p.y -= 26 * dt; break;
      }
    }
  };

  function chunkShape(ctx, p, s) {
    const pal = JUICE[p.type] || JUICE.apple;
    ctx.fillStyle = pal[p.pick % 3 === 2 ? 1 : 0];
    switch (p.type) {
      case 'orange': ctx.beginPath(); ctx.arc(0, 0, s, 0.2, Math.PI - 0.2); ctx.closePath(); ctx.fill(); ctx.stroke(); break;
      case 'banana': ctx.fillStyle = p.pick === 0 ? '#fff06a' : '#f2c10a'; ctx.beginPath(); ctx.moveTo(-s * 1.4, 0); ctx.quadraticCurveTo(0, s * 1.2, s * 1.4, 0); ctx.quadraticCurveTo(0, s * 0.3, -s * 1.4, 0); ctx.fill(); ctx.stroke(); break;
      case 'chili': ctx.fillStyle = p.pick === 1 ? '#ffd54a' : '#ff6a2a'; ctx.beginPath(); ctx.moveTo(0, -s * 1.3); ctx.quadraticCurveTo(s, 0, 0, s); ctx.quadraticCurveTo(-s, 0, 0, -s * 1.3); ctx.fill(); break;
      case 'pineapple': ctx.fillStyle = p.pick === 0 ? '#39b24d' : '#ffd24d'; ctx.beginPath(); ctx.moveTo(0, -s * 1.3); ctx.lineTo(s * 0.6, s * 0.6); ctx.lineTo(-s * 0.6, s * 0.6); ctx.closePath(); ctx.fill(); ctx.stroke(); break;
      case 'melon': case 'boss': ctx.fillStyle = '#ff4f6e'; ctx.beginPath(); ctx.arc(0, 0, s * 1.1, 0, Math.PI); ctx.closePath(); ctx.fill(); ctx.strokeStyle = '#1f9a3d'; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(0, 0, s * 1.1, 0, Math.PI); ctx.stroke(); ctx.fillStyle = '#222'; ctx.beginPath(); ctx.arc(-s * 0.3, s * 0.4, 1.8, 0, TAU); ctx.arc(s * 0.35, s * 0.5, 1.8, 0, TAU); ctx.fill(); break;
      case 'blueberry': ctx.beginPath(); ctx.arc(0, 0, s * 0.55, 0, TAU); ctx.fill(); break;
      case 'cherry': ctx.beginPath(); ctx.arc(0, 0, s * 0.6, 0, TAU); ctx.fill(); ctx.stroke(); break;
      default: // apple
        if (p.pick === 0) { ctx.fillStyle = '#46c75a'; ctx.beginPath(); ctx.ellipse(0, 0, s, s * 0.45, 0, 0, TAU); ctx.fill(); ctx.stroke(); }
        else { ctx.fillStyle = p.pick === 1 ? '#ff5a6e' : '#fff3d6'; ctx.beginPath(); ctx.moveTo(0, -s); ctx.lineTo(s * 0.9, s * 0.7); ctx.lineTo(-s * 0.9, s * 0.7); ctx.closePath(); ctx.fill(); ctx.stroke(); }
    }
  }

  FX.drawLow = function (ctx) { ctx.drawImage(FX.stainCv, 0, 0, FX.W, FX.H); };

  FX.draw = function (ctx) {
    for (const p of FX.parts) {
      const u = p.life / p.max;
      switch (p.k) {
        case 'drop':
          ctx.globalAlpha = Math.min(1, u * 2.2); ctx.fillStyle = p.col; ctx.beginPath(); ctx.arc(p.x, p.y, p.size * (0.4 + u * 0.6), 0, TAU); ctx.fill();
          ctx.fillStyle = 'rgba(255,255,255,.55)'; ctx.beginPath(); ctx.arc(p.x - p.size * 0.25, p.y - p.size * 0.25, p.size * 0.2, 0, TAU); ctx.fill(); break;
        case 'chunk':
          ctx.save(); ctx.globalAlpha = Math.min(1, u * 2); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.strokeStyle = INK; ctx.lineWidth = 2; ctx.lineJoin = 'round';
          chunkShape(ctx, p, p.size * (0.6 + u * 0.4)); ctx.restore(); break;
        case 'spark':
          ctx.globalAlpha = u; ctx.strokeStyle = p.col; ctx.lineWidth = p.w * u; ctx.lineCap = 'round';
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - p.vx * 0.035, p.y - p.vy * 0.035); ctx.stroke(); break;
        case 'conf': {
          ctx.save(); ctx.globalAlpha = Math.min(1, u * 3); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.scale(1, Math.cos(p.flip));
          ctx.fillStyle = p.col; ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); ctx.restore(); break;
        }
        case 'eye': {
          const s = p.size, a = Math.min(1, u * 3);
          ctx.globalAlpha = a * 0.25; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.ellipse(p.x + 2, p.y + 4, s, s * 0.45, 0, 0, TAU); ctx.fill();
          ctx.globalAlpha = a; ctx.fillStyle = '#fff'; ctx.strokeStyle = INK; ctx.lineWidth = 2.2;
          ctx.beginPath(); ctx.arc(p.x, p.y - p.z, s, 0, TAU); ctx.fill(); ctx.stroke();
          const pa = p.pa + (p.z > 1 ? p.life * 8 : 0);
          ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(p.x + Math.cos(pa) * s * 0.35, p.y - p.z + Math.sin(pa) * s * 0.35, s * 0.42, 0, TAU); ctx.fill(); break;
        }
        case 'ring':
          ctx.globalAlpha = Math.min(1, u * 1.6); ctx.strokeStyle = p.col; ctx.lineWidth = Math.max(1, p.w * u);
          ctx.beginPath(); ctx.arc(p.x, p.y, p.r1 * (1 - u * u) + 6, 0, TAU); ctx.stroke(); break;
        case 'flash': {
          ctx.globalAlpha = u; const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * (1.4 - u * 0.4));
          g.addColorStop(0, '#fff'); g.addColorStop(0.5, p.col); g.addColorStop(1, 'rgba(255,255,255,0)');
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 1.4, 0, TAU); ctx.fill(); break;
        }
        case 'beam': {
          ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.ang); ctx.globalAlpha = Math.min(1, u * 2);
          const wdt = 30 * u + 4, g = ctx.createLinearGradient(0, -wdt, 0, wdt);
          g.addColorStop(0, 'rgba(255,240,100,0)'); g.addColorStop(0.5, '#fffbd0'); g.addColorStop(1, 'rgba(255,240,100,0)');
          ctx.fillStyle = g; ctx.fillRect(-p.len, -wdt, p.len * 2, wdt * 2); ctx.restore(); break;
        }
        case 'text': {
          const age = 1 - u, pop = age < 0.18 ? 0.4 + 0.9 * (age / 0.18) + Math.sin(age / 0.18 * Math.PI) * 0.35 : 1;
          ctx.save(); ctx.globalAlpha = Math.min(1, u * 3); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.scale(pop, pop);
          ctx.font = `900 ${p.size}px "Arial Rounded MT Bold","Trebuchet MS",Verdana,sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.lineJoin = 'round'; ctx.lineWidth = p.size * 0.26; ctx.strokeStyle = p.stroke; ctx.strokeText(p.str, 0, 0);
          ctx.fillStyle = p.col; ctx.fillText(p.str, 0, 0); ctx.restore(); break;
        }
        case 'quip': {
          ctx.save(); ctx.globalAlpha = Math.min(1, u * 3); ctx.font = '800 17px "Trebuchet MS",Verdana,sans-serif'; ctx.textAlign = 'center';
          const w = ctx.measureText(p.str).width + 16;
          ctx.fillStyle = '#fff'; ctx.strokeStyle = INK; ctx.lineWidth = 2.5;
          ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(p.x - w / 2, p.y - 18, w, 26, 12); else ctx.rect(p.x - w / 2, p.y - 18, w, 26); ctx.fill(); ctx.stroke();
          ctx.fillStyle = INK; ctx.fillText(p.str, p.x, p.y); ctx.restore(); break;
        }
      }
      ctx.globalAlpha = 1;
    }
  };
})(window);
