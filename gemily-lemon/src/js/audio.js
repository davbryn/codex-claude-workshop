/* Procedural audio: a funky little band + juicy SFX, all synthesized with WebAudio (no asset files). */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};
  const A = G.Audio = { ctx: null, musicOn: true, sfxOn: true, intensity: 1, song: 0, mode: 'menu' };
  let master, comp, musicBus, sfxBus, delay, delayWet, noiseBuf, timer = null;
  let nextT = 0, step = 0, bar = 0, lastDuck = 0;

  const PENT = [0, 2, 4, 7, 9];
  const CHORDS = { maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10], dom: [0, 4, 7, 10], maj: [0, 4, 7, 12] };
  // root = semitones above C3 (130.81Hz); prog = [rootOffset, chordType]
  const SONGS = [
    { bpm: 112, swing: 0.16, root: 0, prog: [[0, 'maj7'], [9, 'm7'], [5, 'maj7'], [7, 'dom']],
      motif: [0, -1, 2, -1, 4, 2, -1, 0, 3, -1, 2, -1, 4, -1, 1, -1] },
    { bpm: 124, swing: 0.1, root: 2, prog: [[0, 'maj7'], [7, 'dom'], [9, 'm7'], [5, 'maj7']],
      motif: [4, -1, 3, 2, -1, 3, -1, 4, 2, -1, 0, -1, 2, 3, -1, -1] },
    { bpm: 132, swing: 0.0, root: 3, prog: [[9, 'm7'], [5, 'maj7'], [0, 'maj7'], [7, 'dom']],
      motif: [2, 4, -1, 2, 0, -1, 2, -1, 3, 4, -1, 3, 2, -1, 0, -1] },
    { bpm: 118, swing: 0.2, root: 5, prog: [[0, 'maj7'], [5, 'maj7'], [9, 'm7'], [7, 'dom']],
      motif: [0, 2, 4, -1, 2, -1, 4, 3, -1, 2, -1, 0, 1, -1, 2, -1] }
  ];
  const mtof = m => 130.8128 * Math.pow(2, m / 12);

  A.init = function () {
    if (A.ctx) return;
    const AC = root.AudioContext || root.webkitAudioContext;
    if (!AC) return;
    const c = A.ctx = new AC();
    master = c.createGain(); master.gain.value = 0.85;
    comp = c.createDynamicsCompressor();
    comp.threshold.value = -16; comp.knee.value = 18; comp.ratio.value = 4; comp.attack.value = 0.004; comp.release.value = 0.2;
    master.connect(comp); comp.connect(c.destination);
    musicBus = c.createGain(); musicBus.gain.value = A.musicOn ? 0.5 : 0; musicBus.connect(master);
    sfxBus = c.createGain(); sfxBus.gain.value = A.sfxOn ? 0.95 : 0; sfxBus.connect(master);
    delay = c.createDelay(1); delay.delayTime.value = 0.2;
    const fb = c.createGain(); fb.gain.value = 0.32;
    delayWet = c.createGain(); delayWet.gain.value = 0.28;
    delay.connect(fb); fb.connect(delay); delay.connect(delayWet); delayWet.connect(musicBus);
    const len = c.sampleRate;
    noiseBuf = c.createBuffer(1, len, c.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  };
  A.resume = function () { if (A.ctx && A.ctx.state !== 'running') A.ctx.resume(); };
  A.setMusic = function (on) { A.musicOn = on; if (musicBus) musicBus.gain.setTargetAtTime(on ? 0.5 : 0, A.ctx.currentTime, 0.05); };
  A.setSfx = function (on) { A.sfxOn = on; if (sfxBus) sfxBus.gain.setTargetAtTime(on ? 0.95 : 0, A.ctx.currentTime, 0.05); };
  A.duck = function (amt) {
    if (!A.ctx || !musicBus || !A.musicOn) return;
    const t = A.ctx.currentTime;
    if (t - lastDuck < 0.05) return; lastDuck = t;
    musicBus.gain.cancelScheduledValues(t);
    musicBus.gain.setValueAtTime(0.5 * (1 - (amt || 0.5)), t);
    musicBus.gain.linearRampToValueAtTime(0.5, t + 0.28);
  };

  // ---- synth helpers
  function osc(type, f, t, dur, vol, o) {
    o = o || {};
    const c = A.ctx, os = c.createOscillator(), g = c.createGain();
    os.type = type; os.frequency.setValueAtTime(f, t);
    if (o.to) os.frequency.exponentialRampToValueAtTime(Math.max(20, o.to), t + (o.glide || dur));
    if (o.detune) os.detune.value = o.detune;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t + (o.a || 0.006));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    let out = g;
    os.connect(g);
    if (o.lp) { const fl = c.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.setValueAtTime(o.lp, t); if (o.lpTo) fl.frequency.exponentialRampToValueAtTime(o.lpTo, t + dur); g.connect(fl); out = fl; }
    out.connect(o.dest || sfxBus);
    if (o.send) { const s = c.createGain(); s.gain.value = o.send; out.connect(s); s.connect(delay); }
    os.start(t); os.stop(t + dur + 0.05);
  }
  function noise(t, dur, vol, o) {
    o = o || {};
    const c = A.ctx, src = c.createBufferSource(), g = c.createGain(), f = c.createBiquadFilter();
    src.buffer = noiseBuf; src.loop = true;
    f.type = o.type || 'bandpass'; f.frequency.setValueAtTime(o.f0 || 1500, t); f.Q.value = o.q || 1;
    if (o.f1) f.frequency.exponentialRampToValueAtTime(o.f1, t + dur);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f); f.connect(g); g.connect(o.dest || sfxBus);
    src.start(t, Math.random() * 0.5); src.stop(t + dur + 0.05);
  }
  const now = () => A.ctx.currentTime;
  const ok = () => A.ctx && A.sfxOn;
  const pent = (i, base) => (base || 261.63) * Math.pow(2, (PENT[i % 5] + 12 * Math.floor(i / 5)) / 12);

  // ---- SFX
  A.pop = function (type, depth) {
    if (!ok()) return;
    const t = now(), n = Math.min(depth || 0, 14), f = pent(n, 330);
    A.duck(0.3 + Math.min(0.3, n * 0.03));
    switch (type) {
      case 'banana':   // slide whistle slip
        osc('sine', f * 2, t, 0.35, 0.3, { to: f * 0.5 }); noise(t, 0.12, 0.25, { f0: 3000, f1: 800, q: 2 }); break;
      case 'chili':    // sizzle + whoomp
        noise(t, 0.5, 0.4, { f0: 5000, f1: 700, q: 0.7 }); osc('sawtooth', 220, t, 0.4, 0.22, { to: 55, lp: 1200 }); osc('sine', f, t, 0.15, 0.2); break;
      case 'pineapple': case 'melon': case 'boss':
        osc('sine', 150, t, 0.5, 0.7, { to: 36 }); noise(t, 0.35, 0.5, { type: 'lowpass', f0: 2600, f1: 200 }); osc('triangle', f * 0.5, t, 0.3, 0.25);
        if (type === 'boss') { osc('sine', 80, t, 1.2, 0.8, { to: 25 }); noise(t, 1.0, 0.5, { type: 'lowpass', f0: 3200, f1: 120 }); }
        break;
      case 'cherry': case 'blueberry':
        osc('sine', f * 1.5, t, 0.12, 0.35, { to: f * 2.2 }); noise(t, 0.08, 0.3, { f0: 2400, q: 3 }); break;
      default:         // squishy splat + rising bell
        osc('sine', 260, t, 0.16, 0.5, { to: 70 }); noise(t, 0.16, 0.45, { f0: 1800, f1: 400, q: 1.2 });
        osc('triangle', f, t + 0.02, 0.28, 0.28, { send: 0.3 }); osc('sine', f * 2, t + 0.02, 0.18, 0.12);
    }
  };
  A.hit = function (speed) { if (!ok()) return; const t = now(), v = Math.min(1, speed / 900); osc('sine', 420 - v * 150, t, 0.09, 0.15 + v * 0.35, { to: 120 }); noise(t, 0.04, 0.1 + v * 0.2, { f0: 2500, q: 2 }); };
  A.wall = function (speed) { if (!ok()) return; const t = now(), v = Math.min(1, speed / 900); osc('triangle', 180 + Math.random() * 40, t, 0.12, 0.12 + v * 0.2, { to: 90 }); };
  A.bump = function () { if (!ok()) return; const t = now(); osc('square', 300, t, 0.2, 0.18, { to: 900, lp: 3000 }); osc('sine', 900, t + 0.04, 0.2, 0.2, { to: 1500, send: 0.3 }); };
  A.launch = function (p) { if (!ok()) return; const t = now(); noise(t, 0.25, 0.25 + p * 0.2, { f0: 400, f1: 3500 + p * 3000, q: 1.5 }); osc('sine', 200 + p * 100, t, 0.18, 0.4, { to: 600 + p * 600 }); };
  A.charge = function (p) { if (!ok()) return; const t = now(); osc('triangle', 220 + p * 500, t, 0.07, 0.05, { lp: 2000 }); };
  A.pocket = function () { if (!ok()) return; const t = now(); osc('sine', 900, t, 0.35, 0.3, { to: 150 }); [0, 0.07, 0.14].forEach((d, i) => osc('triangle', pent(5 + i * 2, 330), t + 0.1 + d, 0.2, 0.2, { send: 0.3 })); };
  A.scratch = function () { if (!ok()) return; const t = now(); osc('sawtooth', 400, t, 0.6, 0.3, { to: 60, lp: 1500 }); osc('square', 90, t + 0.3, 0.3, 0.2, { to: 50 }); };
  A.prime = function () { if (!ok()) return; const t = now(); osc('square', 1200 + Math.random() * 400, t, 0.05, 0.05, { lp: 4000 }); };
  A.portal = function () { if (!ok()) return; const t = now(); osc('sine', 300, t, 0.3, 0.3, { to: 1400, send: 0.4 }); osc('sine', 1400, t + 0.1, 0.3, 0.2, { to: 300 }); };
  A.beam = function () { if (!ok()) return; const t = now(); osc('sawtooth', 1800, t, 0.3, 0.2, { to: 200, lp: 3000, lpTo: 300 }); noise(t, 0.3, 0.2, { f0: 6000, f1: 500 }); };
  A.zest = function () { if (!ok()) return; const t = now(); osc('square', 880, t, 0.25, 0.2, { to: 110, lp: 2500 }); noise(t, 0.2, 0.3, { f0: 5000, f1: 800 }); };
  A.mega = function () { if (!ok()) return; const t = now(); for (let i = 0; i < 10; i++) osc('triangle', pent(i * 1, 220), t + i * 0.06, 0.3, 0.25, { send: 0.4 }); };
  A.ui = function () { if (!ok()) return; const t = now(); osc('triangle', 660, t, 0.08, 0.25, { to: 990 }); };
  A.back = function () { if (!ok()) return; const t = now(); osc('triangle', 520, t, 0.09, 0.22, { to: 330 }); };
  A.blip = function (seed) { if (!ok()) return; const t = now(); osc('square', 330 + (seed % 7) * 38 + Math.random() * 20, t, 0.05, 0.07, { lp: 2400 }); };
  A.gold = function () { if (!ok()) return; const t = now(); [0, 2, 4, 7, 9].forEach((d, i) => osc('triangle', pent(d + 5, 330), t + i * 0.05, 0.4, 0.22, { send: 0.5 })); };
  A.slotTick = function (i) { if (!ok()) return; const t = now(); osc('square', 500 + (i % 3) * 120, t, 0.03, 0.08, { lp: 3000 }); };
  A.slotStop = function (i) { if (!ok()) return; const t = now(); osc('triangle', pent(3 + i * 2, 330), t, 0.25, 0.3, { send: 0.3 }); noise(t, 0.05, 0.2, { f0: 3000, q: 3 }); };
  A.jackpot = function () {
    if (!ok()) return; const t = now(); A.duck(0.7);
    for (let i = 0; i < 16; i++) osc('triangle', pent(i % 10 + 2, 330), t + i * 0.06, 0.35, 0.22, { send: 0.5 });
    osc('sawtooth', 110, t, 0.8, 0.25, { lp: 700 }); noise(t, 0.6, 0.25, { f0: 6000, f1: 2000 });
  };
  A.star = function (i) { if (!ok()) return; const t = now(); osc('triangle', pent(4 + i * 2, 440), t, 0.5, 0.35, { send: 0.5 }); osc('sine', pent(9 + i * 2, 440), t, 0.4, 0.15); };
  A.fanfare = function () {
    if (!ok()) return; const t = now(); A.duck(0.8);
    [[0, 0], [0.12, 2], [0.24, 4], [0.36, 7], [0.55, 9], [0.7, 12]].forEach(([d, s]) => {
      osc('square', 261.63 * Math.pow(2, s / 12), t + d, 0.35, 0.16, { lp: 3500, send: 0.3 });
      osc('triangle', 130.81 * Math.pow(2, s / 12), t + d, 0.4, 0.2);
    });
  };
  A.whoosh = function () { if (!ok()) return; const t = now(); noise(t, 0.5, 0.25, { f0: 300, f1: 3000, q: 1 }); };
  A.slowmo = function () { if (!ok()) return; const t = now(); osc('sine', 600, t, 0.7, 0.25, { to: 60 }); };

  // ---- music: lookahead scheduler
  function sched(t, s, b) {
    const song = SONGS[A.song], c = A.ctx, I = A.intensity;
    const sixteenth = 60 / song.bpm / 4;
    const sw = (s % 2 === 1) ? song.swing * sixteenth : 0;
    t += sw;
    const [ro, ct] = song.prog[b % 4];
    const rootM = song.root + ro;       // semitones over C3
    const chord = CHORDS[ct];
    const hi = A.mode === 'menu' ? 0 : 1;
    // drums
    const kick = [1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 0, 0][s];
    if (kick) { osc('sine', 130, t, 0.22, 0.9, { to: 42, dest: musicBus }); noise(t, 0.02, 0.15, { f0: 1800, q: 1, dest: musicBus }); }
    if (s === 4 || s === 12) { noise(t, 0.16, 0.38, { f0: 1900, f1: 1200, q: 0.8, dest: musicBus }); osc('triangle', 190, t, 0.1, 0.3, { to: 120, dest: musicBus }); }
    if (I >= 2 && (s === 15 || (s === 10 && b % 2 === 1))) noise(t, 0.08, 0.16, { f0: 2200, q: 1, dest: musicBus });
    if (s % 2 === 0) noise(t, s === 14 ? 0.12 : 0.035, s % 4 === 2 ? 0.1 : 0.06, { type: 'highpass', f0: 7500, q: 0.5, dest: musicBus });
    if (I >= 1 && s % 2 === 1) noise(t, 0.025, 0.035, { type: 'highpass', f0: 8500, q: 0.5, dest: musicBus });
    // bass
    const bassPat = { 0: 0, 3: 0, 6: 7, 8: 0, 10: 12, 11: 7, 14: 5 };
    if (s in bassPat) {
      const m = rootM + bassPat[s] - 12;
      osc('sawtooth', mtof(m), t, 0.2, 0.32, { lp: 520, lpTo: 180, dest: musicBus });
      osc('sine', mtof(m), t, 0.22, 0.4, { dest: musicBus });
    }
    // chord stabs
    if (I >= 1 && (s === 3 || s === 6 || s === 10 || s === 13)) {
      chord.forEach((iv, i) => {
        osc('square', mtof(rootM + iv + 12), t, 0.16, 0.05, { detune: i * 4 - 6, lp: 2400, lpTo: 600, dest: musicBus });
        osc('sawtooth', mtof(rootM + iv + 12), t, 0.16, 0.035, { detune: 7 - i * 3, lp: 1800, lpTo: 500, dest: musicBus });
      });
    }
    // pad
    if (s === 0) {
      chord.forEach((iv, i) => osc('triangle', mtof(rootM + iv + 12), t, sixteenth * 15, 0.04, { a: 0.1, lp: 1400, detune: i * 5, dest: musicBus }));
    }
    // lead
    const deg = song.motif[s];
    if (deg >= 0 && (I >= 2 || (A.mode === 'menu' && b % 2 === 1))) {
      const shift = (b % 4 === 3) ? 1 : (b % 4 === 1 ? 0 : 0);
      const idx = deg + shift;
      const m = song.root + 12 + PENT[idx % 5] + 12 * Math.floor(idx / 5) + 12;
      osc('square', mtof(m), t, 0.17, 0.05, { lp: 3200, lpTo: 900, send: 0.45, dest: musicBus, detune: 3 });
      osc('triangle', mtof(m + 12), t, 0.12, 0.03, { send: 0.4, dest: musicBus });
    }
    if (I >= 3 && s % 4 === 2) {   // sparkle arp
      const m = song.root + 24 + chord[(s / 2 + b) % 4 | 0];
      osc('triangle', mtof(m), t, 0.12, 0.05, { send: 0.5, dest: musicBus });
    }
    if (I >= 3 && s === 0 && b % 2 === 0) noise(t, 0.5, 0.08, { type: 'highpass', f0: 6000, f1: 9000, dest: musicBus });
    void c; void hi;
  }
  function tick() {
    if (!A.ctx || !A.playing) return;
    const song = SONGS[A.song], sixteenth = 60 / song.bpm / 4;
    while (nextT < A.ctx.currentTime + 0.14) {
      sched(Math.max(nextT, A.ctx.currentTime), step, bar);
      nextT += sixteenth; step++;
      if (step >= 16) { step = 0; bar++; }
    }
  }
  A.play = function (songIdx, mode) {
    if (!A.ctx) return;
    A.song = songIdx % SONGS.length; A.mode = mode || 'game';
    delay.delayTime.value = 60 / SONGS[A.song].bpm * 0.75;
    if (!A.playing) { A.playing = true; nextT = A.ctx.currentTime + 0.08; step = 0; bar = 0; timer = setInterval(tick, 30); }
    else { step = 0; bar = 0; nextT = A.ctx.currentTime + 0.08; }
  };
  A.stop = function () { A.playing = false; if (timer) clearInterval(timer); timer = null; };
  A.setIntensity = function (i) { A.intensity = i; };
})(window);
