# Gemily Lemon's Last Stand

A mobile-first chain-reaction pool game in the browser. Pull Lemmy the lemon back, let go, and pop the Fruit Mafia.
Cartoon fruits with faces (they blink, glance at each other, flinch, panic) explode in chain reactions with
googly eyes flying off, juice stains, confetti, screen shake and a WebGL shader pass (shockwave ripples,
chromatic aberration, bloom, jackpot rainbow). Gemily narrates.

**Play:** open `index.html` (single self-contained file, works offline, from a phone or GitHub Pages).

- Endless levels in 4 worlds (Lounge, Bumper Bar, Portal Patio, Jelly Lagoon), a boss every 6th level.
- 8 fruit types with different explosions (banana beam, cherry pits, chili blast, 2-hit pineapple/melon...).
- Twists: golden fruit (x5), pockets (x2), bumpers, portals, ice, jelly, vortex, chain-bonus slot machine,
  Zest Bomb, Hint (solver-powered), and the **Mega Squeeze** rescue so no level can ever be stuck.
- Procedural music + SFX (WebAudio, no assets) that intensify with chains.

## Dev
```
node tools/build.js          # src/ -> index.html
node tools/verify.js 1 36    # headless solver proves levels are winnable; --write updates par table
```
