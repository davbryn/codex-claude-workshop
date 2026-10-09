/* Gemily Lemon's Last Stand - deterministic physics + chain reaction core.
   No randomness in here: the hint solver replays shots with the exact same steps the live game uses. */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};

  const W = 720, H = 1040, L = 46, T = 46, R = 674, B = 994, MIDY = 520;
  const POCKETS = [[L, T], [R, T], [L, B], [R, B], [L, MIDY], [R, MIDY]].map(p => ({ x: p[0], y: p[1] }));
  const CAP = 50;
  const DT = 1 / 120;
  const STOP = 14;
  G.TABLE = { W, H, L, T, R, B, MIDY, POCKETS, CAP };
  G.DT = DT;

  // blast = shockwave radius, pts = base score, m = mass, hp = hits to pop
  const FRUITS = {
    apple:     { r: 30, hp: 1, blast: 100, pts: 100, m: 1.0,  name: 'Apple' },
    orange:    { r: 31, hp: 1, blast: 108, pts: 120, m: 1.05, name: 'Orange' },
    cherry:    { r: 23, hp: 1, blast: 74,  pts: 140, m: 0.6,  pits: 3, name: 'Cherry' },
    banana:    { r: 27, hp: 1, blast: 66,  pts: 160, m: 0.9,  beam: 340, name: 'Banana' },
    chili:     { r: 26, hp: 1, blast: 128, pts: 180, m: 0.8,  hot: true, name: 'Chili' },
    pineapple: { r: 35, hp: 2, blast: 118, pts: 220, m: 1.4,  name: 'Pineapple' },
    blueberry: { r: 19, hp: 1, blast: 70,  pts: 80,  m: 0.4,  name: 'Blueberry' },
    melon:     { r: 42, hp: 2, blast: 150, pts: 300, m: 2.0,  pits: 5, name: 'Melon' },
    boss:      { r: 66, hp: 6, blast: 215, pts: 2000, m: 5.0, pits: 10, name: 'Big Melon' },
    lemon:     { r: 30, hp: 99, blast: 0, pts: 0, m: 1.6, name: 'Lemon' },
    pit:       { r: 9,  hp: 1, blast: 0, pts: 0, m: 0.15, name: 'Pit' }
  };
  for (const k in FRUITS) if (k !== 'pit' && k !== 'lemon') FRUITS[k].r = Math.round(FRUITS[k].r * 1.12);
  FRUITS.lemon.r = 34;
  G.FRUITS = FRUITS;

  const THR_LEMON = 95;    // impact speed for the lemon to pop a fruit
  const THR_FRUIT = 310;   // fruit-on-fruit impacts that pop
  const PHYS_FIELDS = ['id', 'type', 'x', 'y', 'vx', 'vy', 'r', 'm', 'hp', 'alive', 'fuse', 'fuseSrc', 'mega',
    'gold', 'ang', 'ang0', 'portalCd', 'life', 'depth', 'accel'];

  class World {
    constructor(level) {
      this.level = level;
      this.bodies = [];
      this.time = 0;
      this.nextId = 1;
      this.emit = true;
      this.events = [];
      this.score = 0;
      this.shots = 0;
      this.pops = 0;
      this.shotPops = 0;
      this.shotScore = 0;
      this.maxDepth = 0;
      this.cueRespawn = -1;
      this.scratches = 0;
      this.bumpHits = 0;
      this.bumpers = level.bumpers || [];
      this.blocks = level.blocks || [];
      this.portals = level.portals || [];
      this.zones = level.zones || [];
      this.vortex = level.vortex || [];
      this.dmgQ = [];
      for (const f of level.fruits) this.addFruit(f.type, f.x, f.y, f);
      this.cue = this.addBody('lemon', level.lemon.x, level.lemon.y);
    }

    addBody(type, x, y, extra) {
      const d = FRUITS[type];
      const b = {
        id: this.nextId++, type, x, y, vx: 0, vy: 0, r: d.r, m: d.m, hp: d.hp, alive: true,
        fuse: -1, fuseSrc: null, mega: false, gold: false, maxHp: d.hp, ang: 0, ang0: 0, portalCd: 0, life: 0, depth: 0, accel: 0
      };
      if (extra) Object.assign(b, extra);
      this.bodies.push(b);
      return b;
    }
    addFruit(type, x, y, f) {
      return this.addBody(type, x, y, { gold: !!(f && f.gold), ang0: (f && f.ang) || 0 });
    }
    fruits() { return this.bodies.filter(b => b.alive && b.type !== 'lemon' && b.type !== 'pit'); }
    fruitCount() {
      let n = 0;
      for (const b of this.bodies) if (b.alive && b.type !== 'lemon' && b.type !== 'pit') n++;
      return n;
    }
    ev(e) { if (this.emit) this.events.push(e); }

    shoot(angle, power) {
      const c = this.cue;
      const sp = 260 + 1500 * Math.max(0, Math.min(1, power));
      c.vx = Math.cos(angle) * sp; c.vy = Math.sin(angle) * sp;
      this.shots++; this.shotPops = 0; this.shotScore = 0; this.maxDepth = 0;
      this.ev({ t: 'shoot', power, x: c.x, y: c.y });
    }

    isSettled() {
      if (this.cueRespawn > 0) return false;
      for (const b of this.bodies) {
        if (!b.alive) continue;
        if (b.vx !== 0 || b.vy !== 0 || b.fuse >= 0 || b.type === 'pit') return false;
      }
      return this.dmgQ.length === 0;
    }

    damage(b, amt, src) {
      if (!b.alive || b.type === 'lemon' || b.type === 'pit') return;
      b.hp -= amt;
      if (src) b.depth = Math.max(b.depth, src.type === 'lemon' ? 0 : src.depth + 1);
      if (b.hp <= 0) this.detonate(b, false);
      else { b.fuse = -1; this.ev({ t: 'hurt', b }); }
    }

    prime(g, delay, src, push) {
      if (!g.alive || g.type === 'lemon' || g.type === 'pit') return;
      if (g.fuse < 0 || delay < g.fuse) {
        if (g.fuse < 0) this.ev({ t: 'prime', b: g });
        g.fuse = delay; g.fuseSrc = src;
      }
    }

    detonate(b, pocket) {
      if (!b.alive) return;
      b.alive = false; b.fuse = -1;
      const d = FRUITS[b.type];
      const depth = b.depth;
      this.pops++; this.shotPops++;
      if (depth > this.maxDepth) this.maxDepth = depth;
      let pts = d.pts * (1 + 0.35 * depth) * (1 + 0.15 * (this.shotPops - 1));
      if (pocket) pts *= 2;
      if (b.gold) pts *= 5;
      pts = Math.round(pts / 10) * 10;
      this.score += pts; this.shotScore += pts;
      this.ev({ t: 'boom', b, x: b.x, y: b.y, type: b.type, depth, pocket, gold: b.gold, pts, n: this.shotPops, blast: d.blast });

      // shockwave: push + light the fuse on everything inside the blast radius
      const blast = d.blast;
      for (const g of this.bodies) {
        if (!g.alive || g === b || g.type === 'pit') continue;
        const dx = g.x - b.x, dy = g.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.001;
        if (dist > blast) continue;
        const k = 1 - Math.min(1, dist / (blast + g.r));
        const strength = (d.hot ? 470 : 320) * (b.type === 'boss' ? 1.4 : 1);
        const f = (g.type === 'lemon' ? 0.45 : 1) * strength * k / Math.sqrt(g.m);
        g.vx += dx / dist * f; g.vy += dy / dist * f;
        if (g.type !== 'lemon') {
          const delay = (d.hot ? 0.06 : 0.1) + 0.16 * (dist / blast);
          g.depth = Math.max(g.depth, depth + 1);
          this.prime(g, delay, b);
        }
      }
      if (d.beam) {
        const dirx = Math.cos(b.ang0), diry = Math.sin(b.ang0);
        this.ev({ t: 'beam', x: b.x, y: b.y, ang: b.ang0, len: d.beam });
        for (const g of this.bodies) {
          if (!g.alive || g === b || g.type === 'lemon' || g.type === 'pit') continue;
          const dx = g.x - b.x, dy = g.y - b.y;
          const along = dx * dirx + dy * diry;
          const perp = Math.abs(dx * diry - dy * dirx);
          if (Math.abs(along) < d.beam && perp < 26 + g.r) {
            g.depth = Math.max(g.depth, depth + 1);
            this.prime(g, 0.07 + Math.abs(along) * 0.0004, b);
            const s = along >= 0 ? 1 : -1;
            g.vx += dirx * s * 260 / Math.sqrt(g.m); g.vy += diry * s * 260 / Math.sqrt(g.m);
          }
        }
      }
      if (d.pits) {
        const n = d.pits;
        for (let i = 0; i < n; i++) {
          const a = b.ang0 + 0.5 + i * Math.PI * 2 / n;
          const sp = b.type === 'boss' ? 620 : 520;
          this.addBody('pit', b.x + Math.cos(a) * (b.r * 0.6), b.y + Math.sin(a) * (b.r * 0.6),
            { vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, life: 0.62, depth: depth });
        }
      }
    }

    popCue() {
      const c = this.cue;
      c.alive = false; c.vx = c.vy = 0;
      this.cueRespawn = 0.7;
      this.scratches++;
      this.ev({ t: 'scratch', x: c.x, y: c.y });
    }
    respawnCue() {
      const c = this.cue, s = this.level.lemon;
      let x = s.x, y = s.y;
      for (let tries = 0; tries < 40; tries++) {
        let ok = true;
        for (const b of this.bodies) {
          if (!b.alive || b === c || b.type === 'pit') continue;
          if (Math.hypot(b.x - x, b.y - y) < b.r + c.r + 6) { ok = false; break; }
        }
        if (ok) break;
        x = s.x + ((tries % 2) ? 1 : -1) * (70 + tries * 14);
        y = s.y - (tries % 3) * 30;
        x = Math.max(L + 40, Math.min(R - 40, x));
      }
      c.x = x; c.y = y; c.vx = c.vy = 0; c.alive = true;
      this.ev({ t: 'respawn', x, y });
    }

    // Mega Squeeze: the rescue move that makes every level winnable
    megaSqueeze() {
      const list = this.fruits().sort((a, b) => Math.hypot(a.x - this.cue.x, a.y - this.cue.y) - Math.hypot(b.x - this.cue.x, b.y - this.cue.y));
      this.shots++; this.shotPops = 0; this.shotScore = 0; this.maxDepth = 0;
      list.forEach((g, i) => { g.mega = true; g.fuse = 0.25 + i * 0.13; g.depth = i; });
      this.ev({ t: 'mega' });
    }
    zestBomb(g) {
      this.shots++; this.shotPops = 0; this.shotScore = 0; this.maxDepth = 0;
      g.hp = 0; g.depth = 0;
      this.ev({ t: 'zest', b: g });
      this.detonate(g, false);
    }

    step() {
      const dt = DT;
      this.time += dt;
      const bs = this.bodies;
      let n = bs.length;
      if (this.cueRespawn > 0) { this.cueRespawn -= dt; if (this.cueRespawn <= 0) { this.cueRespawn = -1; this.respawnCue(); } }

      for (let i = 0; i < n; i++) {
        const b = bs[i];
        if (b.alive && b.fuse >= 0) {
          b.fuse -= dt;
          if (b.fuse <= 0) { b.fuse = -1; this.damage(b, b.mega ? 99 : 1, b.fuseSrc); }
        }
      }
      n = bs.length;

      // integrate
      for (let i = 0; i < n; i++) {
        const b = bs[i];
        if (!b.alive) continue;
        let ax = 0, ay = 0;
        for (const v of this.vortex) {
          const dx = v.x - b.x, dy = v.y - b.y, d = Math.hypot(dx, dy);
          if (d < v.r && d > 1) {
            const k = (1 - d / v.r) * Math.min(1, d / 40) * v.s;
            ax += dx / d * k - dy / d * k * 0.55; ay += dy / d * k + dx / d * k * 0.55;
          }
        }
        let kf = 1.0, cf = 140;
        if (b.type === 'pit') { kf = 0.15; cf = 0; }
        else for (const z of this.zones) {
          if (b.x > z.x - z.w / 2 && b.x < z.x + z.w / 2 && b.y > z.y - z.h / 2 && b.y < z.y + z.h / 2) { kf = z.k; cf = z.c; }
        }
        b.vx += ax * dt; b.vy += ay * dt;
        b.accel = Math.hypot(ax, ay);
        let sp = Math.hypot(b.vx, b.vy);
        if (sp > 0) {
          const ns = Math.max(0, sp - (kf * sp + cf) * dt);
          const s = ns / sp; b.vx *= s; b.vy *= s; sp = ns;
          if (sp < STOP && b.accel < cf) { b.vx = 0; b.vy = 0; sp = 0; }
        } else if (b.accel > cf) { /* pushed out of rest by a vortex */ }
        b.x += b.vx * dt; b.y += b.vy * dt;
        if (b.type !== 'banana') b.ang += (b.vx * 0.5 + b.vy * 0.2) * dt / b.r;
        if (b.portalCd > 0) b.portalCd -= dt;
        if (b.type === 'pit') { b.life -= dt; if (b.life <= 0) { b.alive = false; } }
      }

      // portals
      if (this.portals.length) {
        for (let i = 0; i < n; i++) {
          const b = bs[i];
          if (!b.alive || b.portalCd > 0 || b.type === 'pit') continue;
          for (const p of this.portals) {
            const da = Math.hypot(b.x - p.a.x, b.y - p.a.y), db = Math.hypot(b.x - p.b.x, b.y - p.b.y);
            let from = null, to = null;
            if (da < 26) { from = p.a; to = p.b; } else if (db < 26) { from = p.b; to = p.a; }
            if (from) {
              const sp = Math.hypot(b.vx, b.vy) || 1;
              b.x = to.x + b.vx / sp * 34; b.y = to.y + b.vy / sp * 34;
              b.portalCd = 0.5;
              this.ev({ t: 'portal', fx: from.x, fy: from.y, tx: to.x, ty: to.y, b });
              break;
            }
          }
        }
      }

      // walls
      for (let i = 0; i < n; i++) {
        const b = bs[i];
        if (!b.alive) continue;
        const e = b.type === 'pit' ? 1 : 0.88, r = b.r;
        let hit = 0;
        if (b.x < L + r) { b.x = L + r; if (b.vx < 0) { hit = -b.vx; b.vx = -b.vx * e; } }
        else if (b.x > R - r) { b.x = R - r; if (b.vx > 0) { hit = b.vx; b.vx = -b.vx * e; } }
        if (b.y < T + r) { b.y = T + r; if (b.vy < 0) { hit = Math.max(hit, -b.vy); b.vy = -b.vy * e; } }
        else if (b.y > B - r) { b.y = B - r; if (b.vy > 0) { hit = Math.max(hit, b.vy); b.vy = -b.vy * e; } }
        if (hit > 90 && b.type !== 'pit') this.ev({ t: 'wall', x: b.x, y: b.y, speed: hit, b });
      }

      // bumpers + blocks
      for (let i = 0; i < n; i++) {
        const b = bs[i];
        if (!b.alive || b.type === 'pit') continue;
        for (const bp of this.bumpers) {
          const dx = b.x - bp.x, dy = b.y - bp.y, rr = b.r + bp.r, d2 = dx * dx + dy * dy;
          if (d2 < rr * rr && d2 > 0) {
            const d = Math.sqrt(d2), nx = dx / d, ny = dy / d;
            b.x = bp.x + nx * rr; b.y = bp.y + ny * rr;
            const vn = b.vx * nx + b.vy * ny;
            if (vn < 0) { b.vx -= 2 * vn * nx; b.vy -= 2 * vn * ny; }
            b.vx += nx * 230; b.vy += ny * 230;
            this.bumpHits++;
            this.ev({ t: 'bump', x: bp.x, y: bp.y, bp, b });
          }
        }
        for (const bl of this.blocks) {
          const x0 = bl.x - bl.w / 2, x1 = bl.x + bl.w / 2, y0 = bl.y - bl.h / 2, y1 = bl.y + bl.h / 2;
          const cx = Math.max(x0, Math.min(x1, b.x)), cy = Math.max(y0, Math.min(y1, b.y));
          let dx = b.x - cx, dy = b.y - cy;
          const d2 = dx * dx + dy * dy;
          if (d2 < b.r * b.r) {
            let nx, ny;
            if (d2 > 0.0001) { const d = Math.sqrt(d2); nx = dx / d; ny = dy / d; b.x = cx + nx * b.r; b.y = cy + ny * b.r; }
            else {
              const pl = b.x - x0, pr = x1 - b.x, pt = b.y - y0, pb = y1 - b.y, m = Math.min(pl, pr, pt, pb);
              if (m === pl) { nx = -1; ny = 0; b.x = x0 - b.r; } else if (m === pr) { nx = 1; ny = 0; b.x = x1 + b.r; }
              else if (m === pt) { nx = 0; ny = -1; b.y = y0 - b.r; } else { nx = 0; ny = 1; b.y = y1 + b.r; }
            }
            const vn = b.vx * nx + b.vy * ny;
            if (vn < 0) {
              b.vx -= 1.9 * vn * nx; b.vy -= 1.9 * vn * ny;
              if (-vn > 90) this.ev({ t: 'wall', x: b.x, y: b.y, speed: -vn, b });
            }
          }
        }
      }

      // body vs body
      const q = this.dmgQ;
      for (let i = 0; i < n; i++) {
        const a = bs[i];
        if (!a.alive) continue;
        for (let j = i + 1; j < n; j++) {
          const b = bs[j];
          if (!b.alive) continue;
          const at = a.type, bt = b.type;
          if (at === 'pit' && (bt === 'pit' || bt === 'lemon')) continue;
          if (bt === 'pit' && at === 'lemon') continue;
          const dx = b.x - a.x, dy = b.y - a.y, rr = a.r + b.r;
          if (dx > rr || dx < -rr || dy > rr || dy < -rr) continue;
          const d2 = dx * dx + dy * dy;
          if (d2 >= rr * rr || d2 === 0) continue;
          const d = Math.sqrt(d2), nx = dx / d, ny = dy / d;
          const ov = rr - d, tot = a.m + b.m;
          a.x -= nx * ov * b.m / tot; a.y -= ny * ov * b.m / tot;
          b.x += nx * ov * a.m / tot; b.y += ny * ov * a.m / tot;
          const rvn = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny;
          if (rvn > 0) {
            if (at === 'pit' || bt === 'pit') {
              const pit = at === 'pit' ? a : b, fr = at === 'pit' ? b : a;
              if (rvn > 40) { q.push([fr, 1, pit]); pit.alive = false; fr.vx += pit.vx * 0.12; fr.vy += pit.vy * 0.12; this.ev({ t: 'pitpop', x: pit.x, y: pit.y }); }
              continue;
            }
            const e = 0.9, imp = (1 + e) * rvn / (1 / a.m + 1 / b.m);
            a.vx -= imp * nx / a.m; a.vy -= imp * ny / a.m;
            b.vx += imp * nx / b.m; b.vy += imp * ny / b.m;
            if (rvn > 30) this.ev({ t: 'hit', x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, speed: rvn, a, b, nx, ny });
            if (at === 'lemon' || bt === 'lemon') {
              const fr = at === 'lemon' ? b : a, lm = at === 'lemon' ? a : b;
              if (rvn >= THR_LEMON) q.push([fr, 1, lm]);
            } else if (rvn >= THR_FRUIT) {
              q.push([a, 1, b]); q.push([b, 1, a]);
            }
          }
        }
      }
      if (q.length) {
        for (let k = 0; k < q.length; k++) this.damage(q[k][0], q[k][1], q[k][2]);
        q.length = 0;
      }

      // pockets (with a gentle funnel pull so slow fruit drops in)
      for (let i = 0; i < bs.length; i++) {
        const b = bs[i];
        if (!b.alive) continue;
        for (const p of POCKETS) {
          const dx = p.x - b.x, dy = p.y - b.y, d = Math.hypot(dx, dy);
          if (d < CAP) {
            if (b.type === 'lemon') this.popCue();
            else if (b.type === 'pit') b.alive = false;
            else { this.ev({ t: 'pocket', b, x: p.x, y: p.y }); b.x = p.x; b.y = p.y; this.detonate(b, true); }
            break;
          } else if (d < CAP + 46 && b.type !== 'pit' && b.type !== 'lemon') {
            const sp = Math.hypot(b.vx, b.vy);
            if (sp < 240) { b.vx += dx / d * 1500 * dt; b.vy += dy / d * 1500 * dt; }
          }
        }
      }

      // compact
      let w = 0;
      for (let i = 0; i < bs.length; i++) { const b = bs[i]; if (b.alive || b === this.cue) bs[w++] = b; }
      bs.length = w;
    }

    clone() {
      const w = Object.create(World.prototype);
      w.level = this.level; w.time = this.time; w.nextId = this.nextId; w.emit = false; w.events = [];
      w.score = this.score; w.shots = this.shots; w.pops = this.pops; w.shotPops = this.shotPops; w.shotScore = this.shotScore;
      w.maxDepth = this.maxDepth; w.cueRespawn = this.cueRespawn; w.scratches = this.scratches; w.bumpHits = this.bumpHits;
      w.bumpers = this.bumpers; w.blocks = this.blocks; w.portals = this.portals; w.zones = this.zones; w.vortex = this.vortex;
      w.dmgQ = [];
      w.bodies = this.bodies.map(b => {
        const c = {};
        for (const k of PHYS_FIELDS) c[k] = b[k];
        return c;
      });
      w.cue = w.bodies.find(b => b.type === 'lemon');
      return w;
    }
  }
  G.World = World;

  // aim preview: where would the lemon first touch something, with up to 2 wall bounces
  G.rayPreview = function (world, dirx, diry) {
    const c = world.cue;
    let x = c.x, y = c.y, dx = dirx, dy = diry;
    const pts = [{ x, y }];
    const fr = world.bodies.filter(b => b.alive && b.type !== 'lemon' && b.type !== 'pit');
    let hit = null, bounces = 0, travelled = 0;
    const step = 5;
    for (let i = 0; i < 520 && !hit; i++) {
      x += dx * step; y += dy * step; travelled += step;
      for (const f of fr) {
        if ((f.x - x) * (f.x - x) + (f.y - y) * (f.y - y) < (f.r + c.r) * (f.r + c.r)) { hit = f; break; }
      }
      if (hit) break;
      let bounced = false;
      for (const bp of world.bumpers) {
        const ddx = x - bp.x, ddy = y - bp.y, rr = c.r + bp.r;
        if (ddx * ddx + ddy * ddy < rr * rr) {
          const d = Math.hypot(ddx, ddy) || 1, nx = ddx / d, ny = ddy / d, vn = dx * nx + dy * ny;
          if (vn < 0) { dx -= 2 * vn * nx; dy -= 2 * vn * ny; bounced = true; }
        }
      }
      for (const bl of world.blocks) {
        const cx = Math.max(bl.x - bl.w / 2, Math.min(bl.x + bl.w / 2, x)), cy = Math.max(bl.y - bl.h / 2, Math.min(bl.y + bl.h / 2, y));
        const ddx = x - cx, ddy = y - cy;
        if (ddx * ddx + ddy * ddy < c.r * c.r) {
          const d = Math.hypot(ddx, ddy) || 1, nx = ddx / d, ny = ddy / d, vn = dx * nx + dy * ny;
          if (vn < 0) { dx -= 2 * vn * nx; dy -= 2 * vn * ny; bounced = true; }
        }
      }
      if (x < L + c.r) { x = L + c.r; dx = Math.abs(dx); bounced = true; }
      else if (x > R - c.r) { x = R - c.r; dx = -Math.abs(dx); bounced = true; }
      if (y < T + c.r) { y = T + c.r; dy = Math.abs(dy); bounced = true; }
      else if (y > B - c.r) { y = B - c.r; dy = -Math.abs(dy); bounced = true; }
      if (bounced) { pts.push({ x, y }); bounces++; if (bounces > 2) break; }
    }
    pts.push({ x, y });
    return { pts, hit, x, y };
  };

  // ---- solver: replays shots on cloned worlds (used for Hint, par calculation and level verification)
  G.simShot = function (world, ang, power) {
    const w = world.clone();
    w.shoot(ang, power);
    let calm = 0;
    for (let i = 0; i < 1200; i++) {
      w.step();
      if (w.isSettled()) { if (++calm > 8) break; } else calm = 0;
    }
    return w;
  };
  G.scoreSim = function (w, before) {
    const left = w.fruitCount();
    return w.shotPops * 100 + (left === 0 ? 8000 : 0) - (w.scratches - before.scratches) * 250 + Math.min(w.maxDepth, 12) * 15;
  };
  G.shotCandidates = function (world) {
    const c = world.cue, fr = world.fruits(), out = [];
    for (const f of fr) {
      const a = Math.atan2(f.y - c.y, f.x - c.x);
      for (const off of [-0.075, 0, 0.075]) for (const p of [0.55, 1.0]) out.push([a + off, p]);
    }
    for (let k = 0; k < 28; k++) for (const p of [0.7, 1.0]) out.push([k * Math.PI * 2 / 28 + 0.05, p]);
    return out;
  };
  G.findBestShot = function (world) {
    const cands = G.shotCandidates(world);
    let best = null;
    for (const [a, p] of cands) {
      const w = G.simShot(world, a, p), s = G.scoreSim(w, world);
      if (!best || s > best.score) best = { angle: a, power: p, score: s, pops: w.shotPops, left: w.fruitCount() };
    }
    if (best) {
      const base = best;
      for (const da of [-0.035, -0.018, 0.018, 0.035]) for (const p of [base.power * 0.8, base.power, Math.min(1, base.power * 1.15)]) {
        const w = G.simShot(world, base.angle + da, p), s = G.scoreSim(w, world);
        if (s > best.score) best = { angle: base.angle + da, power: p, score: s, pops: w.shotPops, left: w.fruitCount() };
      }
    }
    return best;
  };
  // incremental version for the browser: call .run(ms) until .done
  G.makeSolver = function (world) {
    const cands = G.shotCandidates(world);
    const st = { i: 0, best: null, done: false, total: cands.length, refine: null };
    st.run = function (ms) {
      const t0 = performance.now();
      while (!st.done && performance.now() - t0 < ms) {
        if (st.i < cands.length) {
          const [a, p] = cands[st.i++];
          const w = G.simShot(world, a, p), s = G.scoreSim(w, world);
          if (!st.best || s > st.best.score) st.best = { angle: a, power: p, score: s, pops: w.shotPops, left: w.fruitCount() };
        } else {
          if (!st.refine && st.best) {
            const b = st.best; st.refine = [];
            for (const da of [-0.035, -0.018, 0.018, 0.035]) for (const p of [b.power * 0.8, b.power, Math.min(1, b.power * 1.15)]) st.refine.push([b.angle + da, p]);
            st.total += st.refine.length;
          }
          if (st.refine && st.refine.length) {
            const [a, p] = st.refine.shift(); st.i++;
            const w = G.simShot(world, a, p), s = G.scoreSim(w, world);
            if (s > st.best.score) st.best = { angle: a, power: p, score: s, pops: w.shotPops, left: w.fruitCount() };
          } else st.done = true;
        }
      }
      return st;
    };
    return st;
  };
})(typeof window !== 'undefined' ? window : globalThis);
