/* Procedural cartoon fruit: bodies + expressive faces (blink, look, flinch, panic). */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};
  const Art = G.Art = {};
  const INK = '#2a0f3a';
  const TAU = Math.PI * 2;

  Art.PAL = {
    apple: ['#ff6a6a', '#d1203f', '#ff9a9a'], orange: ['#ffbb4d', '#f2780c', '#ffd89a'], cherry: ['#f0306b', '#8a0c37', '#ff8fb0'],
    banana: ['#fff06a', '#f2c10a', '#fff8b0'], chili: ['#ff5a3c', '#b8001e', '#ff9d7a'], pineapple: ['#ffd24d', '#e98a00', '#fff0a0'],
    blueberry: ['#7a8cff', '#2d2fa8', '#b8c2ff'], melon: ['#58d66b', '#17802f', '#b6f5b0'], boss: ['#58d66b', '#17802f', '#b6f5b0'],
    lemon: ['#fff77a', '#f5c400', '#ffffff'], pit: ['#8b5a2b', '#4a2a10', '#c08a50']
  };

  function grad(ctx, r, c0, c1, ox, oy) {
    const g = ctx.createRadialGradient(-r * (ox || 0.35), -r * (oy || 0.4), r * 0.1, 0, 0, r * 1.05);
    g.addColorStop(0, c0); g.addColorStop(1, c1);
    return g;
  }
  function ink(ctx, w) { ctx.lineWidth = w || 3; ctx.strokeStyle = INK; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; }
  function leaf(ctx, x, y, len, ang, col) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    ctx.fillStyle = col || '#46c75a';
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.quadraticCurveTo(len * 0.5, -len * 0.45, len, 0); ctx.quadraticCurveTo(len * 0.5, len * 0.4, 0, 0); ctx.fill();
    ink(ctx, 2.2); ctx.stroke();
    ctx.restore();
  }
  function shine(ctx, r, a) {
    ctx.save(); ctx.globalAlpha = a || 0.5; ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.ellipse(-r * 0.42, -r * 0.5, r * 0.2, r * 0.12, -0.7, 0, TAU); ctx.fill();
    ctx.globalAlpha = (a || 0.5) * 0.6; ctx.beginPath(); ctx.arc(-r * 0.12, -r * 0.72, r * 0.05, 0, TAU); ctx.fill();
    ctx.restore();
  }

  const BODY = {
    apple(ctx, r) {
      ctx.fillStyle = grad(ctx, r, '#ff7b7b', '#cf1c3d');
      ctx.beginPath(); ctx.moveTo(0, -r * 0.82);
      ctx.bezierCurveTo(r * 0.5, -r * 1.12, r * 1.1, -r * 0.5, r * 1.0, r * 0.15);
      ctx.bezierCurveTo(r * 0.95, r * 0.85, r * 0.4, r * 1.05, 0, r * 0.92);
      ctx.bezierCurveTo(-r * 0.4, r * 1.05, -r * 0.95, r * 0.85, -r * 1.0, r * 0.15);
      ctx.bezierCurveTo(-r * 1.1, -r * 0.5, -r * 0.5, -r * 1.12, 0, -r * 0.82); ctx.fill(); ink(ctx); ctx.stroke();
      ink(ctx, 3.2); ctx.beginPath(); ctx.moveTo(0, -r * 0.82); ctx.quadraticCurveTo(r * 0.08, -r * 1.05, r * 0.28, -r * 1.25); ctx.stroke();
      leaf(ctx, r * 0.1, -r * 0.98, r * 0.62, -0.5);
      shine(ctx, r);
    },
    orange(ctx, r) {
      ctx.fillStyle = grad(ctx, r, '#ffc766', '#ee6f00');
      ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.fill(); ink(ctx); ctx.stroke();
      ctx.fillStyle = 'rgba(160,60,0,.28)';
      for (let i = 0; i < 12; i++) { const a = i * 2.4, d = r * (0.35 + (i % 4) * 0.14); ctx.beginPath(); ctx.arc(Math.cos(a) * d, Math.sin(a) * d + r * 0.05, r * 0.035, 0, TAU); ctx.fill(); }
      ctx.fillStyle = '#3aa84a'; ctx.beginPath(); ctx.arc(0, -r * 0.96, r * 0.1, 0, TAU); ctx.fill(); ink(ctx, 2); ctx.stroke();
      leaf(ctx, 0, -r * 0.97, r * 0.55, -0.35); shine(ctx, r);
    },
    cherry(ctx, r) {
      ink(ctx, 3.4); ctx.beginPath(); ctx.moveTo(0, -r * 0.7); ctx.bezierCurveTo(r * 0.1, -r * 1.5, r * 0.7, -r * 1.8, r * 1.15, -r * 1.75); ctx.stroke();
      ctx.strokeStyle = '#4fae4a'; ctx.lineWidth = 1.6; ctx.stroke();
      leaf(ctx, r * 0.85, -r * 1.7, r * 0.75, -0.25);
      ctx.fillStyle = grad(ctx, r, '#ff5d8d', '#8a0c37');
      ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.fill(); ink(ctx); ctx.stroke();
      ctx.fillStyle = 'rgba(80,0,20,.4)'; ctx.beginPath(); ctx.ellipse(0, -r * 0.82, r * 0.22, r * 0.1, 0, 0, TAU); ctx.fill();
      shine(ctx, r, 0.6);
    },
    banana(ctx, r, b) {
      ctx.save(); ctx.rotate(b ? b.ang0 : 0);
      const L = r * 1.65, th = r * 0.78;
      const path = () => { ctx.beginPath(); ctx.moveTo(-L, -r * 0.1); ctx.quadraticCurveTo(0, r * 1.15, L, -r * 0.1); ctx.quadraticCurveTo(0, r * 0.15 - th * 0.4, -L, -r * 0.1); ctx.closePath(); };
      path();
      const g = ctx.createLinearGradient(0, -th, 0, th); g.addColorStop(0, '#fff7a0'); g.addColorStop(1, '#f2b705');
      ctx.fillStyle = g; ctx.fill(); ink(ctx); ctx.stroke();
      ctx.fillStyle = '#6b4a1e';
      ctx.beginPath(); ctx.arc(-L, -r * 0.1, r * 0.13, 0, TAU); ctx.fill(); ctx.beginPath(); ctx.arc(L, -r * 0.1, r * 0.13, 0, TAU); ctx.fill();
      ctx.restore();
    },
    chili(ctx, r) {
      ctx.save(); ctx.rotate(-0.35);
      ctx.fillStyle = grad(ctx, r, '#ff6e4d', '#b1001d');
      ctx.beginPath(); ctx.moveTo(-r * 0.7, -r * 0.55);
      ctx.bezierCurveTo(-r * 0.6, -r * 1.0, r * 0.7, -r * 1.0, r * 0.8, -r * 0.45);
      ctx.bezierCurveTo(r * 1.0, r * 0.4, r * 1.2, r * 1.1, r * 1.9, r * 1.35);
      ctx.bezierCurveTo(r * 0.9, r * 1.5, -r * 0.2, r * 1.1, -r * 0.7, r * 0.3);
      ctx.bezierCurveTo(-r * 1.0, -r * 0.1, -r * 0.9, -r * 0.4, -r * 0.7, -r * 0.55); ctx.fill(); ink(ctx); ctx.stroke();
      ctx.fillStyle = '#35b24a'; ctx.beginPath(); ctx.moveTo(-r * 0.55, -r * 0.8); ctx.quadraticCurveTo(0, -r * 1.35, r * 0.6, -r * 0.8); ctx.quadraticCurveTo(0, -r * 0.55, -r * 0.55, -r * 0.8); ctx.fill(); ink(ctx, 2.4); ctx.stroke();
      ink(ctx, 3); ctx.beginPath(); ctx.moveTo(0, -r * 1.05); ctx.quadraticCurveTo(r * 0.2, -r * 1.6, r * 0.65, -r * 1.7); ctx.stroke();
      ctx.restore(); shine(ctx, r * 0.9, 0.45);
    },
    pineapple(ctx, r) {
      const spikes = (col) => {
        ctx.fillStyle = col;
        for (let i = -3; i <= 3; i++) {
          ctx.beginPath(); ctx.moveTo(i * r * 0.18 - r * 0.14, -r * 0.8); ctx.lineTo(i * r * 0.26, -r * (1.5 - Math.abs(i) * 0.1)); ctx.lineTo(i * r * 0.18 + r * 0.14, -r * 0.8); ctx.fill(); ink(ctx, 2); ctx.stroke();
        }
      };
      spikes('#39b24d');
      ctx.fillStyle = grad(ctx, r, '#ffe27a', '#e58a00');
      ctx.beginPath(); ctx.ellipse(0, r * 0.05, r * 0.92, r * 1.0, 0, 0, TAU); ctx.fill(); ink(ctx); ctx.stroke();
      ctx.save(); ctx.beginPath(); ctx.ellipse(0, r * 0.05, r * 0.92, r * 1.0, 0, 0, TAU); ctx.clip();
      ctx.strokeStyle = 'rgba(150,80,0,.4)'; ctx.lineWidth = 1.8;
      for (let i = -6; i <= 6; i++) { ctx.beginPath(); ctx.moveTo(i * r * 0.32 - r, -r); ctx.lineTo(i * r * 0.32 + r, r); ctx.stroke(); ctx.beginPath(); ctx.moveTo(i * r * 0.32 + r, -r); ctx.lineTo(i * r * 0.32 - r, r); ctx.stroke(); }
      ctx.restore(); shine(ctx, r);
    },
    blueberry(ctx, r) {
      ctx.fillStyle = grad(ctx, r, '#8d9cff', '#2a2b9e');
      ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.fill(); ink(ctx); ctx.stroke();
      ctx.fillStyle = '#1b1c6e'; ctx.beginPath();
      for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * 0.12 : r * 0.3; ctx.lineTo(Math.cos(a) * rr, -r * 0.8 + Math.sin(a) * rr * 0.6); }
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,.25)'; ctx.beginPath(); ctx.ellipse(0, r * 0.1, r * 0.8, r * 0.7, 0, 0, TAU); ctx.fill();
      shine(ctx, r, 0.7);
    },
    melon(ctx, r, b) {
      ctx.fillStyle = grad(ctx, r, '#7bec7e', '#14782c');
      ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.fill(); ink(ctx, b && b.type === 'boss' ? 4 : 3); ctx.stroke();
      ctx.save(); ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.clip();
      ctx.strokeStyle = 'rgba(8,70,25,.55)'; ctx.lineWidth = r * 0.14; ctx.lineCap = 'round';
      for (let i = -3; i <= 3; i++) { ctx.beginPath(); ctx.moveTo(i * r * 0.36, -r); ctx.bezierCurveTo(i * r * 0.9, -r * 0.35, i * r * 0.9, r * 0.35, i * r * 0.36, r); ctx.stroke(); }
      ctx.restore(); shine(ctx, r, 0.4);
      if (b && b.hp < b.maxHp) {   // cracks
        ink(ctx, 2.4); ctx.strokeStyle = '#ff4d5e';
        const k = (b.maxHp - b.hp);
        for (let i = 0; i < Math.min(5, k + 1); i++) { const a = i * 1.7 + 0.5; ctx.beginPath(); ctx.moveTo(Math.cos(a) * r * 0.5, Math.sin(a) * r * 0.5); ctx.lineTo(Math.cos(a + 0.2) * r * 0.78, Math.sin(a + 0.2) * r * 0.78); ctx.lineTo(Math.cos(a - 0.1) * r * 1.0, Math.sin(a - 0.1) * r * 1.0); ctx.stroke(); }
      }
      if (b && b.type === 'boss') {   // crown
        ctx.fillStyle = '#ffd23c';
        ctx.beginPath(); ctx.moveTo(-r * 0.5, -r * 0.82); ctx.lineTo(-r * 0.56, -r * 1.35); ctx.lineTo(-r * 0.25, -r * 1.08); ctx.lineTo(0, -r * 1.45); ctx.lineTo(r * 0.25, -r * 1.08); ctx.lineTo(r * 0.56, -r * 1.35); ctx.lineTo(r * 0.5, -r * 0.82); ctx.closePath(); ctx.fill(); ink(ctx, 3); ctx.stroke();
        ctx.fillStyle = '#ff3d7a'; ctx.beginPath(); ctx.arc(0, -r * 1.0, r * 0.08, 0, TAU); ctx.fill();
      }
    },
    lemon(ctx, r) {
      ctx.save(); ctx.rotate(-0.18);
      ctx.fillStyle = grad(ctx, r, '#fffa96', '#f3bf00', 0.3, 0.35);
      ctx.beginPath(); ctx.moveTo(-r * 1.2, 0);
      ctx.bezierCurveTo(-r * 1.05, -r * 0.35, -r * 0.8, -r * 0.98, 0, -r * 0.98);
      ctx.bezierCurveTo(r * 0.8, -r * 0.98, r * 1.05, -r * 0.35, r * 1.2, 0);
      ctx.bezierCurveTo(r * 1.05, r * 0.35, r * 0.8, r * 0.98, 0, r * 0.98);
      ctx.bezierCurveTo(-r * 0.8, r * 0.98, -r * 1.05, r * 0.35, -r * 1.2, 0); ctx.fill(); ink(ctx, 3.4); ctx.stroke();
      ctx.restore();
      leaf(ctx, r * 0.55, -r * 0.8, r * 0.6, -0.9);
      shine(ctx, r, 0.6);
      // rebel headband
      ctx.save(); ctx.beginPath(); ctx.ellipse(0, 0, r * 1.05, r * 0.98, 0, 0, TAU); ctx.clip();
      ctx.fillStyle = '#ff2f6a'; ctx.fillRect(-r * 1.3, -r * 0.66, r * 2.6, r * 0.3);
      ctx.fillStyle = 'rgba(255,255,255,.55)'; for (let i = -4; i <= 4; i++) { ctx.beginPath(); ctx.arc(i * r * 0.3, -r * 0.51, r * 0.04, 0, TAU); ctx.fill(); }
      ctx.restore();
      ctx.strokeStyle = INK; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(-r * 0.98, -r * 0.66); ctx.lineTo(-r * 0.98, -r * 0.36); ctx.stroke();
      ctx.fillStyle = '#ff2f6a'; ctx.beginPath(); ctx.moveTo(r * 0.95, -r * 0.55); ctx.quadraticCurveTo(r * 1.4, -r * 0.8, r * 1.65, -r * 0.45); ctx.quadraticCurveTo(r * 1.35, -r * 0.5, r * 1.1, -r * 0.38); ctx.closePath(); ctx.fill(); ink(ctx, 2); ctx.stroke();
    },
    pit(ctx, r) {
      ctx.fillStyle = '#7a4a1e'; ctx.beginPath(); ctx.ellipse(0, 0, r * 1.2, r * 0.8, 0, 0, TAU); ctx.fill(); ink(ctx, 2); ctx.stroke();
      ctx.fillStyle = 'rgba(255,255,255,.4)'; ctx.beginPath(); ctx.ellipse(-r * 0.3, -r * 0.2, r * 0.3, r * 0.15, 0, 0, TAU); ctx.fill();
    }
  };
  BODY.boss = BODY.melon;
  Art.body = function (ctx, type, r, b) { (BODY[type] || BODY.apple)(ctx, r, b); };

  // ---- face
  function eye(ctx, x, y, w, h, v, mood, side) {
    const blink = v.blink || 0;
    ctx.save(); ctx.translate(x, y);
    if (mood === 'ouch' || (mood === 'happy' && v.moodT > 0)) {
      ink(ctx, Math.max(2.2, w * 0.32));
      ctx.beginPath();
      if (mood === 'ouch') { ctx.moveTo(-w * 0.8 * side, -h * 0.8); ctx.lineTo(w * 0.7 * side, 0); ctx.lineTo(-w * 0.8 * side, h * 0.8); }
      else { ctx.arc(0, h * 0.35, w * 0.8, Math.PI * 1.1, Math.PI * 1.9); }
      ctx.stroke(); ctx.restore(); return;
    }
    const sq = mood === 'focus' ? 0.72 : 1;
    const hh = h * (1 - blink * 0.94) * sq;
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.ellipse(0, 0, w, Math.max(0.8, hh), 0, 0, TAU); ctx.fill();
    ink(ctx, Math.max(1.6, w * 0.17)); ctx.stroke();
    if (blink < 0.7) {
      const pr = w * (mood === 'panic' ? 0.32 : mood === 'scared' ? 0.4 : 0.56);
      const lx = v.look.x * (w - pr) * 0.85, ly = v.look.y * (h - pr * 0.6) * 0.85 + (mood === 'panic' ? Math.sin(v.t * 60) * 1.2 : 0);
      ctx.save(); ctx.beginPath(); ctx.ellipse(0, 0, w * 0.94, Math.max(0.8, hh * 0.94), 0, 0, TAU); ctx.clip();
      ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(lx, ly, pr, 0, TAU); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(lx - pr * 0.3, ly - pr * 0.35, pr * 0.3, 0, TAU); ctx.fill();
      ctx.restore();
    }
    ctx.restore();
  }
  function brow(ctx, x, y, w, ang) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ink(ctx, Math.max(2.4, w * 0.28));
    ctx.beginPath(); ctx.moveTo(-w, 0); ctx.lineTo(w, 0); ctx.stroke(); ctx.restore();
  }

  Art.face = function (ctx, r, v, type) {
    const mood = v.mood || 'idle';
    const big = type === 'boss';
    const es = r * (type === 'blueberry' ? 0.3 : 0.26) * (mood === 'scared' ? 1.18 : mood === 'panic' ? 1.35 : 1);
    const ex = r * 0.38, ey = -r * 0.08, my = r * 0.38;
    const ox = v.look.x * r * 0.1, oy = v.look.y * r * 0.07;
    ctx.save(); ctx.translate(ox, oy);
    if (mood === 'panic') ctx.translate(Math.sin(v.t * 70) * 1.4, Math.cos(v.t * 63) * 1.2);
    if (type === 'lemon') ctx.translate(0, r * 0.1);
    eye(ctx, -ex, ey, es, es * 1.12, v, mood, -1);
    eye(ctx, ex, ey, es, es * 1.12, v, mood, 1);
    // brows
    if (mood === 'focus' || big) { brow(ctx, -ex, ey - es * 1.35, es * 0.9, 0.45); brow(ctx, ex, ey - es * 1.35, es * 0.9, -0.45); }
    else if (mood === 'scared' || mood === 'panic') { brow(ctx, -ex, ey - es * 1.6, es * 0.8, -0.35); brow(ctx, ex, ey - es * 1.6, es * 0.8, 0.35); }
    else if (mood === 'worry') { brow(ctx, -ex, ey - es * 1.5, es * 0.7, -0.3); brow(ctx, ex, ey - es * 1.5, es * 0.7, 0.3); }
    // mouth
    ink(ctx, Math.max(2.2, r * 0.07));
    ctx.fillStyle = '#6b1233';
    const mw = r * 0.3;
    ctx.beginPath();
    if (mood === 'scared') { ctx.ellipse(0, my + r * 0.04, mw * 0.5, mw * 0.65 + Math.sin(v.t * 40) * 0.8, 0, 0, TAU); ctx.fill(); ctx.stroke(); }
    else if (mood === 'panic') { ctx.ellipse(0, my + r * 0.08, mw * 0.85, mw * 1.0, 0, 0, TAU); ctx.fill(); ctx.stroke(); ctx.fillStyle = '#ff7a95'; ctx.beginPath(); ctx.ellipse(0, my + r * 0.28, mw * 0.5, mw * 0.3, 0, 0, TAU); ctx.fill(); }
    else if (mood === 'ouch' || mood === 'worry') { ctx.moveTo(-mw, my + r * 0.06); for (let i = 1; i <= 4; i++) ctx.lineTo(-mw + i * mw * 0.5, my + (i % 2 ? -r * 0.02 : r * 0.1)); ctx.stroke(); }
    else if (mood === 'happy') { ctx.moveTo(-mw * 1.2, my - r * 0.04); ctx.quadraticCurveTo(0, my + r * 0.62, mw * 1.2, my - r * 0.04); ctx.closePath(); ctx.fill(); ctx.stroke(); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.moveTo(-mw * 0.9, my); ctx.quadraticCurveTo(0, my + r * 0.18, mw * 0.9, my); ctx.quadraticCurveTo(0, my + r * 0.05, -mw * 0.9, my); ctx.fill(); }
    else if (mood === 'focus') { ctx.moveTo(-mw, my + r * 0.04); ctx.lineTo(mw, my - r * 0.04); ctx.stroke(); ctx.fillStyle = '#fff'; ctx.fillRect(-mw * 0.4, my - r * 0.03, mw * 0.8, r * 0.07); }
    else if (v.smirk) { ctx.moveTo(-mw, my); ctx.quadraticCurveTo(mw * 0.3, my + r * 0.28, mw * 1.1, my - r * 0.1); ctx.stroke(); }
    else { ctx.moveTo(-mw, my - r * 0.02); ctx.quadraticCurveTo(0, my + r * 0.3, mw, my - r * 0.02); ctx.stroke(); }
    // blush + sweat
    if (mood === 'scared' || mood === 'panic' || mood === 'worry') {
      ctx.fillStyle = 'rgba(120,200,255,.9)'; const sy = (v.t * 40) % 10;
      ctx.beginPath(); ctx.moveTo(r * 0.78, -r * 0.45 + sy * 0.3); ctx.quadraticCurveTo(r * 0.95, -r * 0.2 + sy * 0.3, r * 0.78, -r * 0.1 + sy * 0.3); ctx.quadraticCurveTo(r * 0.6, -r * 0.2 + sy * 0.3, r * 0.78, -r * 0.45 + sy * 0.3); ctx.fill(); ink(ctx, 1.5); ctx.stroke();
    } else if (mood === 'happy' || mood === 'idle') {
      ctx.fillStyle = 'rgba(255,90,130,.28)';
      ctx.beginPath(); ctx.ellipse(-r * 0.62, my - r * 0.08, r * 0.14, r * 0.08, 0, 0, TAU); ctx.fill();
      ctx.beginPath(); ctx.ellipse(r * 0.62, my - r * 0.08, r * 0.14, r * 0.08, 0, 0, TAU); ctx.fill();
    }
    ctx.restore();
  };

  Art.goldAura = function (ctx, r, t) {
    ctx.save();
    const g = ctx.createRadialGradient(0, 0, r * 0.6, 0, 0, r * 1.9);
    g.addColorStop(0, 'rgba(255,230,120,.0)'); g.addColorStop(0.55, 'rgba(255,215,80,.5)'); g.addColorStop(1, 'rgba(255,200,40,0)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, r * 1.9, 0, TAU); ctx.fill();
    ctx.strokeStyle = 'rgba(255,225,90,.95)'; ctx.lineWidth = 3.5; ctx.setLineDash([r * 0.5, r * 0.3]); ctx.lineDashOffset = -t * 30;
    ctx.beginPath(); ctx.arc(0, 0, r * 1.15, 0, TAU); ctx.stroke(); ctx.setLineDash([]);
    for (let i = 0; i < 3; i++) {
      const a = t * 1.4 + i * 2.1, d = r * 1.2, s = r * 0.18 * (0.6 + 0.4 * Math.sin(t * 6 + i * 2));
      Art.star(ctx, Math.cos(a) * d, Math.sin(a) * d, s, '#fff6b0');
    }
    ctx.restore();
  };
  Art.star = function (ctx, x, y, s, col) {
    ctx.fillStyle = col; ctx.beginPath();
    for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4, rr = i % 2 ? s * 0.28 : s; ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
    ctx.closePath(); ctx.fill();
  };
})(window);
