import './style.css';

const $ = (id) => document.getElementById(id);

// Counter
let count = 0;
const fmtCount = (n) => String(n).replace('-', '\u2212'); // typographic minus
const setCount = (n) => {
  count = n;
  $('count').textContent = fmtCount(count);
  $('s-count').textContent = fmtCount(count);
};
$('inc').addEventListener('click', () => setCount(count + 1));
$('dec').addEventListener('click', () => setCount(count - 1));
$('reset').addEventListener('click', () => setCount(0));

// Name generator
const adjectives = [
  'Quantum', 'Angry', 'Suspicious', 'Sleepy', 'Turbo', 'Haunted', 'Sarcastic',
  'Recursive', 'Wobbly', 'Caffeinated', 'Feral', 'Legally Distinct', 'Gluten-Free',
  'Overclocked', 'Passive-Aggressive', 'Majestic', 'Soggy', 'Unhinged',
];
const nouns = [
  'Potato', 'Compiler', 'Toaster', 'Penguin', 'Spreadsheet', 'Llama', 'Kettle',
  'Hamster', 'Mainframe', 'Pickle', 'Goblin', 'Waffle', 'Semicolon', 'Trombone',
  'Cactus', 'Router', 'Badger', 'Croissant',
];
const pick = (list) => list[Math.floor(Math.random() * list.length)];
let namesGenerated = 0;
let lastName = '';
$('generate').addEventListener('click', () => {
  let name;
  do name = `${pick(adjectives)} ${pick(nouns)}`;
  while (name === lastName);
  lastName = name;
  namesGenerated += 1;
  const el = $('name');
  el.textContent = name;
  el.classList.remove('pop');
  void el.offsetWidth; // restart the pop animation
  el.classList.add('pop');
  $('s-names').textContent = namesGenerated;
});

// Bouncing ball
const box = $('box');
const ball = $('ball');
const pos = { x: 20, y: 20 };
const vel = { x: 140, y: 110 }; // px per second
let paused = false;
let last = performance.now();

function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.05);
  last = now;
  if (!paused) {
    const maxX = box.clientWidth - ball.offsetWidth;
    const maxY = box.clientHeight - ball.offsetHeight;
    pos.x += vel.x * dt;
    pos.y += vel.y * dt;
    if (pos.x <= 0 || pos.x >= maxX) { vel.x *= -1; pos.x = Math.max(0, Math.min(pos.x, maxX)); }
    if (pos.y <= 0 || pos.y >= maxY) { vel.y *= -1; pos.y = Math.max(0, Math.min(pos.y, maxY)); }
    ball.style.transform = `translate(${pos.x}px, ${pos.y}px)`;
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

$('pause').addEventListener('click', (e) => {
  paused = !paused;
  e.currentTarget.textContent = paused ? 'Resume' : 'Pause';
  e.currentTarget.setAttribute('aria-pressed', String(paused));
  ball.classList.toggle('paused', paused);
});

// Uptime
const opened = Date.now();
const fmt = (s) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m ${sec}s`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
};
const tick = () => { $('s-uptime').textContent = fmt(Math.floor((Date.now() - opened) / 1000)); };
setInterval(tick, 1000);
tick();
