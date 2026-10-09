/* Gemily Lemon - cartoon narrator (inline SVG, expressive) + her dialogue. */
(function (root) {
  'use strict';
  const G = root.G = root.G || {};
  let uidN = 0;

  function svg(u) {
    return `
<svg class="gem" data-mood="idle" viewBox="0 0 240 300" xmlns="http://www.w3.org/2000/svg" aria-label="Gemily Lemon">
  <defs>
    <linearGradient id="skin${u}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbd5b3"/><stop offset="1" stop-color="#f0b98f"/></linearGradient>
    <linearGradient id="hair${u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4d089"/><stop offset=".6" stop-color="#e5b865"/><stop offset="1" stop-color="#cf9b46"/></linearGradient>
    <linearGradient id="top${u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e6edf4"/></linearGradient>
    <linearGradient id="gold${u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffe69a"/><stop offset=".5" stop-color="#d8a63c"/><stop offset="1" stop-color="#fff1b8"/></linearGradient>
    <radialGradient id="iris${u}" cx=".5" cy=".4" r=".6"><stop offset="0" stop-color="#b9d6e6"/><stop offset="1" stop-color="#5f8fae"/></radialGradient>
  </defs>
  <g class="gem-body">
    <!-- back hair -->
    <path d="M48 130 C38 58 80 20 122 20 C166 20 204 58 196 130 C194 170 202 206 208 236 C170 252 76 252 38 236 C46 206 50 170 48 130 Z" fill="url(#hair${u})" stroke="#b98a3e" stroke-width="2"/>
    <!-- shoulders / skin -->
    <path d="M22 300 C22 258 56 236 96 228 L148 228 C188 236 222 258 222 300 Z" fill="url(#skin${u})" stroke="#c98f6a" stroke-width="2"/>
    <!-- other arm + blue wristband -->
    <path d="M52 258 C46 276 44 290 42 304" stroke="#c98f6a" stroke-width="32" stroke-linecap="round" fill="none"/>
    <path d="M52 258 C46 276 44 290 42 304" stroke="#f3c19b" stroke-width="28" stroke-linecap="round" fill="none"/>
    <g transform="rotate(-8 44 288)"><rect x="26" y="280" width="36" height="16" rx="5" fill="#3b78e0" stroke="#1d3f8f" stroke-width="2"/><text x="44" y="292" font-size="10" font-weight="900" text-anchor="middle" fill="#fff" font-family="Arial Black,Arial,sans-serif">3UE</text></g>
    <!-- top: white with watercolour print -->
    <path d="M42 304 C42 278 62 262 92 258 Q122 286 152 258 C182 262 202 278 202 304 Z" fill="url(#top${u})" stroke="#9aa9b8" stroke-width="2"/>
    <path d="M68 304 C66 288 78 274 98 268 C110 286 96 296 90 304 Z" fill="#8fb0c4" opacity=".75"/>
    <path d="M104 304 C108 288 120 280 138 276 C150 290 138 298 134 304 Z" fill="#b6ccd9" opacity=".8"/>
    <path d="M60 300 L78 268" stroke="#26303c" stroke-width="6" stroke-linecap="round"/>
    <path d="M98 304 L118 282" stroke="#26303c" stroke-width="5" stroke-linecap="round"/>
    <path d="M150 300 L166 276" stroke="#26303c" stroke-width="4" stroke-linecap="round"/>
    <!-- neck -->
    <path d="M102 148 L102 238 Q122 258 142 238 L142 148 Z" fill="#efb68f" stroke="#c98f6a" stroke-width="2"/>
    <ellipse cx="122" cy="176" rx="22" ry="12" fill="#d99b76" opacity=".45"/>
    <!-- pearl pendant -->
    <path d="M98 234 Q122 270 146 234" stroke="#cdd5de" stroke-width="2" fill="none"/>
    <circle cx="122" cy="262" r="5.5" fill="#fff" stroke="#b8c2cc" stroke-width="1.5"/><circle cx="120" cy="260" r="1.6" fill="#fff"/>
  </g>
  <g class="gem-head">
    <!-- face -->
    <path d="M68 100 C68 58 96 42 122 42 C148 42 176 58 176 100 C176 136 158 172 122 174 C86 172 68 136 68 100 Z" fill="url(#skin${u})" stroke="#c98f6a" stroke-width="2"/>
    <ellipse cx="88" cy="132" rx="12" ry="7" fill="#ff8f86" opacity=".38"/><ellipse cx="156" cy="132" rx="12" ry="7" fill="#ff8f86" opacity=".38"/>
    <g fill="#d89a76" opacity=".8">
      <circle cx="84" cy="124" r="1.3"/><circle cx="92" cy="128" r="1.3"/><circle cx="96" cy="121" r="1.2"/><circle cx="88" cy="137" r="1.2"/><circle cx="100" cy="130" r="1.1"/>
      <circle cx="160" cy="124" r="1.3"/><circle cx="152" cy="128" r="1.3"/><circle cx="148" cy="121" r="1.2"/><circle cx="156" cy="137" r="1.2"/><circle cx="144" cy="130" r="1.1"/>
      <circle cx="116" cy="117" r="1.1"/><circle cx="128" cy="117" r="1.1"/><circle cx="122" cy="121" r="1"/>
    </g>
    <!-- brows -->
    <g class="gem-brows" stroke="#b4843e" stroke-width="4" stroke-linecap="round" fill="none">
      <path class="brow-l" d="M84 86 Q99 77 114 85"/><path class="brow-r" d="M130 85 Q145 77 160 86"/>
    </g>
    <!-- eyes -->
    <g class="gem-eyes">
      <g class="gem-eye">
        <ellipse cx="99" cy="103" rx="14.5" ry="12.5" fill="#fff" stroke="#6b4a3a" stroke-width="2"/>
        <circle class="iris" cx="100" cy="104" r="8.6" fill="url(#iris${u})" stroke="#4d7794" stroke-width="1.2"/><circle class="pupil" cx="100" cy="104" r="4.2" fill="#14202b"/><circle cx="103" cy="100.5" r="2.7" fill="#fff"/><circle cx="97" cy="107" r="1.2" fill="#fff"/>
        <path d="M84 100 Q99 88 114 99" stroke="#4a3322" stroke-width="3.6" stroke-linecap="round" fill="none"/>
        <path d="M85 100 L80 96 M87 96.5 L83 91" stroke="#4a3322" stroke-width="2" stroke-linecap="round"/>
      </g>
      <g class="gem-eye">
        <ellipse cx="145" cy="103" rx="14.5" ry="12.5" fill="#fff" stroke="#6b4a3a" stroke-width="2"/>
        <circle class="iris" cx="146" cy="104" r="8.6" fill="url(#iris${u})" stroke="#4d7794" stroke-width="1.2"/><circle class="pupil" cx="146" cy="104" r="4.2" fill="#14202b"/><circle cx="149" cy="100.5" r="2.7" fill="#fff"/><circle cx="143" cy="107" r="1.2" fill="#fff"/>
        <path d="M130 99 Q145 88 160 100" stroke="#4a3322" stroke-width="3.6" stroke-linecap="round" fill="none"/>
        <path d="M159 100 L164 96 M157 96.5 L161 91" stroke="#4a3322" stroke-width="2" stroke-linecap="round"/>
      </g>
    </g>
    <!-- nose -->
    <path d="M120 112 Q126 124 118 127" stroke="#d08f6c" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    <!-- mouths -->
    <g class="mouth m-idle"><path d="M102 142 Q123 160 144 141" stroke="#b5465a" stroke-width="3.6" fill="none" stroke-linecap="round"/><path d="M100 140 L97 137 M146 139 L149 136" stroke="#c98f6a" stroke-width="2" stroke-linecap="round"/><path d="M110 148 Q123 156 136 148 Q123 152 110 148Z" fill="#e47a8a" opacity=".8"/></g>
    <g class="mouth m-talk"><ellipse class="talkmouth" cx="123" cy="148" rx="11" ry="8" fill="#7a2234" stroke="#a53a4d" stroke-width="2"/><ellipse cx="123" cy="153" rx="6" ry="3" fill="#ff8a9a"/><path d="M114 143 Q123 146 132 143 L131 146 Q123 148 115 146Z" fill="#fff"/></g>
    <g class="mouth m-happy"><path d="M100 139 Q123 176 146 139 Z" fill="#7a2234" stroke="#a53a4d" stroke-width="2.4" stroke-linejoin="round"/><path d="M104 141 Q123 152 142 141 L141 145 Q123 156 105 145Z" fill="#fff"/><ellipse cx="123" cy="160" rx="8" ry="4" fill="#ff8a9a"/></g>
    <g class="mouth m-shock"><ellipse cx="123" cy="150" rx="8.5" ry="12" fill="#7a2234" stroke="#a53a4d" stroke-width="2.4"/><ellipse cx="123" cy="156" rx="5" ry="4" fill="#ff8a9a"/></g>
    <g class="mouth m-smug"><path d="M104 144 Q126 158 146 136" stroke="#b5465a" stroke-width="3.6" fill="none" stroke-linecap="round"/><path d="M146 136 L150 133" stroke="#c98f6a" stroke-width="2" stroke-linecap="round"/></g>
    <!-- front hair: centre part -->
    <path d="M123 34 C90 38 62 66 56 112 C52 144 50 178 40 216 C70 204 86 164 88 126 C90 94 104 64 123 34 Z" fill="url(#hair${u})" stroke="#b98a3e" stroke-width="2"/>
    <path d="M121 34 C154 38 182 66 188 112 C192 144 194 178 204 216 C174 204 158 164 156 126 C154 94 140 64 121 34 Z" fill="url(#hair${u})" stroke="#b98a3e" stroke-width="2"/>
    <g fill="none" stroke="#fbe3a8" stroke-width="2.6" stroke-linecap="round" opacity=".9">
      <path d="M112 46 C90 56 76 80 72 112"/><path d="M104 54 C86 72 80 98 78 132"/><path d="M62 128 C60 156 56 180 50 204"/>
      <path d="M134 46 C156 56 170 80 174 112"/><path d="M180 130 C182 156 186 180 192 204"/>
    </g>
    <g fill="none" stroke="#c4903f" stroke-width="2" stroke-linecap="round" opacity=".7"><path d="M70 150 C68 170 64 188 58 206"/><path d="M178 150 C180 170 184 188 190 206"/></g>
    <!-- lemon slice hair clip -->
    <g transform="translate(78 66) rotate(-18)">
      <circle r="13" fill="#ffe94d" stroke="#c99a00" stroke-width="2.4"/><circle r="9.6" fill="#fff6b8"/>
      <g stroke="#f0c400" stroke-width="1.6"><path d="M0 -9 V9 M-9 0 H9 M-6.4 -6.4 L6.4 6.4 M6.4 -6.4 L-6.4 6.4"/></g>
      <path d="M10 -8 q10 -6 14 2 q-8 4 -14 -2z" fill="#45c45a" stroke="#1f7a33" stroke-width="1.6"/>
    </g>
  </g>
  <!-- hand on cheek + gold watch -->
  <g class="gem-hand">
    <path d="M178 170 C186 210 190 250 196 304" stroke="#c98f6a" stroke-width="34" stroke-linecap="round" fill="none"/>
    <path d="M178 170 C186 210 190 250 196 304" stroke="#f3c19b" stroke-width="30" stroke-linecap="round" fill="none"/>
    <g transform="rotate(-10 184 214)"><rect x="162" y="203" width="44" height="22" rx="5" fill="url(#gold${u})" stroke="#9c7420" stroke-width="2"/>
      <path d="M170 203 V225 M178 203 V225 M186 203 V225 M194 203 V225 M202 203 V225" stroke="#b78a2a" stroke-width="1.2"/>
      <rect x="170" y="197" width="26" height="20" rx="6" fill="#20262e" stroke="#e8e8ee" stroke-width="2.4"/><rect x="174" y="201" width="18" height="12" rx="3" fill="#3b6ea5"/></g>
    <ellipse cx="173" cy="158" rx="22" ry="24" transform="rotate(14 173 158)" fill="#f3c19b" stroke="#c98f6a" stroke-width="2"/>
    <g stroke="#c98f6a" stroke-width="11.5" stroke-linecap="round" fill="none">
      <path d="M158 148 C154 140 152 132 151 124"/><path d="M167 144 C165 136 164 128 164 120"/><path d="M177 143 C178 135 179 128 180 120"/><path d="M187 148 C190 141 192 134 194 127"/>
    </g>
    <g stroke="#f6cba7" stroke-width="8.6" stroke-linecap="round" fill="none">
      <path d="M158 148 C154 140 152 132 151 124"/><path d="M167 144 C165 136 164 128 164 120"/><path d="M177 143 C178 135 179 128 180 120"/><path d="M187 148 C190 141 192 134 194 127"/>
    </g>
    <g fill="#ff6fa3" stroke="#d0447f" stroke-width="1"><ellipse cx="151" cy="122" rx="3.8" ry="4.8"/><ellipse cx="164" cy="118" rx="3.8" ry="4.8"/><ellipse cx="180" cy="118" rx="3.8" ry="4.8"/><ellipse cx="194" cy="125" rx="3.6" ry="4.4" transform="rotate(20 194 125)"/></g>
    <g><rect x="160" y="136" width="12" height="4" rx="2" fill="#e8ecf2" stroke="#8a95a3" stroke-width="1"/><circle cx="166" cy="135" r="3.2" fill="#fff" stroke="#8a95a3" stroke-width="1"/></g>
  </g>
  <g class="gem-spark" fill="#fff6a0" stroke="#e0a800" stroke-width="1.5">
    <path d="M30 60 l4 10 10 4 -10 4 -4 10 -4 -10 -10 -4 10 -4z"/><path d="M212 40 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z"/><path d="M206 150 l3 7 7 3 -7 3 -3 7 -3 -7 -7 -3 7 -3z"/>
  </g>
</svg>`;
  }

  const LINES = {
    intro: [
      "Ugh. Not AGAIN. The Fruit Bowl Mafia has taken over my favourite lounge!",
      "They've got faces, attitude and a questionable sense of humour. I've got one lemon.",
      "Meet Lemmy. Pull him back, let go, and watch things go pop. Chain reactions are... juicy.",
      "Clear the table. That's it. This is Gemily Lemon's LAST STAND!"
    ],
    start: ["Pull back and let go. Simple.", "Look at them, smirking. Not for long.", "Aim for the clusters. Boom goes the fruit.", "Bank shots are for show-offs. Be a show-off.", "Lemmy believes in you. I believe in Lemmy.", "Fruit salad is on the menu tonight."],
    tipBumper: "Bumpers! Lemmy loves a good bounce. Use them for trick shots.",
    tipPortal: "Portals! In one side, out the other. Don't ask me how it works.",
    tipIce: "Ice and jelly! Ice is slippery, jelly is sticky. Plan accordingly.",
    tipBanana: "Bananas fire a beam along their length. Aim them at friends!",
    tipCherry: "Cherries spit pits. Tiny, angry, deadly pits.",
    tipChili: "Chilis! Big blast, big feelings. Stand back.",
    tipPineapple: "Pineapples take two hits. They're sturdy and extremely rude.",
    tipBlueberry: "Blueberries. Small. Many. Annoying. Pop one, pop them all.",
    tipMelon: "A melon takes two hits, then it goes BIG.",
    boss: ["The BIG MELON! He's got a crown and six lives. Hit him until he cracks!", "Boss time. He looks tough. He's mostly water."],
    chain3: ["Ooh, chain reaction!", "Look at them go!", "Domino fruit!"],
    chain6: ["THAT'S what I'm talking about!", "Absolute carnage. I love it.", "Did you SEE that?!"],
    chain10: ["UNREAL! Frame that one!", "Juice for everyone!", "I'm not crying, you're crying!"],
    miss: ["Lemmy, focus!", "Whiff. We don't talk about it.", "They're laughing at us...", "Try again, with feeling."],
    scratch: ["Lemmy fell in the pocket! Classic Lemmy.", "Oops. He'll be back. He always is."],
    hint: ["Psst. Try that one.", "Fine, I'll tell you. Over here!", "My lemon-sense is tingling."],
    gold: "A golden one! Shiny. Pop it for a big win!",
    clear: ["Table cleared! You're a natural.", "That's how it's done! Fruit-free again.", "Nailed it. Next!", "Squeaky clean. Well, sticky."],
    clear3: ["PERFECT! Three stars! I might cry.", "Flawless! Frame this level."],
    rescue: "Out of patience? Use the MEGA SQUEEZE. It always works, I promise.",
    zest: "Zest Bomb ready. Tap any fruit to detonate it on the spot."
  };
  G.LINES = LINES;
  const pick = a => a[Math.floor(Math.random() * a.length)];
  G.pick = pick;

  const instances = [];
  const Gem = G.Gemily = {
    make(container, cls) {
      const el = document.createElement('div');
      el.className = 'gem-wrap ' + (cls || '');
      el.innerHTML = svg(++uidN);
      container.appendChild(el);
      instances.push(el);
      // gaze: little pupils drift
      return el;
    },
    mood(m, ms) {
      instances.forEach(el => { const s = el.querySelector('svg'); if (s) s.dataset.mood = m; if (m === 'happy') el.classList.add('cheer'); else el.classList.remove('cheer'); });
      clearTimeout(Gem._mt);
      if (ms) Gem._mt = setTimeout(() => Gem.mood(Gem.talking ? 'talk' : 'idle'), ms);
    },
    bubble: null, textEl: null, typing: null, talking: false, q: null,
    attach(bubbleEl, textEl) { Gem.bubble = bubbleEl; Gem.textEl = textEl; },
    say(text, o) {
      o = o || {};
      if (!Gem.textEl) return;
      clearInterval(Gem.typing); clearTimeout(Gem.hide);
      Gem.bubble.classList.add('show');
      Gem.textEl.textContent = '';
      let i = 0;
      Gem.talking = true; Gem.mood(o.mood === 'happy' || o.mood === 'shock' ? o.mood : 'talk');
      Gem.typing = setInterval(() => {
        i += 1;
        Gem.textEl.textContent = text.slice(0, i);
        if (i % 2 === 0 && G.Audio) G.Audio.blip(i);
        if (i >= text.length) {
          clearInterval(Gem.typing); Gem.talking = false;
          setTimeout(() => { if (!Gem.talking) Gem.mood(o.mood && o.mood !== 'talk' ? o.mood : 'idle', 0); }, 120);
          if (o.onDone) o.onDone();
          if (!o.sticky) Gem.hide = setTimeout(() => Gem.bubble.classList.remove('show'), o.hold || 2600 + text.length * 25);
        }
      }, 28);
    },
    shut() { clearInterval(Gem.typing); Gem.talking = false; if (Gem.bubble) Gem.bubble.classList.remove('show'); Gem.mood('idle'); }
  };
})(window);
