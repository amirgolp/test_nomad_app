// A semicircular gauge. The DOM is built once per component instance and
// updated in place on every refresh, so the bar and target glide to their new
// positions instead of the gauge being redrawn.
const NS = 'http://www.w3.org/2000/svg';
const CX = 110, CY = 104, R = 70;

const point = (f, r) => {
  const angle = Math.PI * (1 - f);
  return [CX + r * Math.cos(angle), CY - r * Math.sin(angle)];
};

const arc = (f0, f1, r) => {
  // Split at the top: a single arc command of exactly 180 degrees is ambiguous.
  const stops = f0 < 0.5 && f1 > 0.5 ? [0.5, f1] : [f1];
  const [x0, y0] = point(f0, r);
  return `M ${x0} ${y0}` + stops.map((f) => {
    const [x, y] = point(f, r);
    return ` A ${r} ${r} 0 0 1 ${x} ${y}`;
  }).join('');
};

const svg = (tag, attrs, parent) => {
  const node = document.createElementNS(NS, tag);
  for (const name in attrs) node.setAttribute(name, attrs[name]);
  if (parent) parent.appendChild(node);
  return node;
};

function build(root) {
  const box = document.createElement('div');
  box.className = 'gauge';
  const title = document.createElement('div');
  title.className = 'title';
  const dial = svg('svg', { viewBox: '0 0 220 124', class: 'dial', role: 'img' });
  svg('path', { class: 'track', d: arc(0, 1, R) }, dial);
  const bands = svg('g', { class: 'bands' }, dial);
  const ticks = svg('g', { class: 'ticks' }, dial);
  const bar = svg('path', { class: 'bar', d: arc(0, 1, R), pathLength: 100 }, dial);
  // Drawn at the start of the axis and rotated into place.
  const target = svg('line', { class: 'target', x1: CX - R - 10, y1: CY, x2: CX - R + 10, y2: CY }, dial);
  const value = svg('text', { class: 'value', x: CX, y: CY - 14 }, dial);
  const unit = svg('text', { class: 'unit', x: CX, y: CY + 6 }, dial);
  const caption = document.createElement('div');
  caption.className = 'caption';
  box.append(title, dial, caption);
  root.appendChild(box);
  return { box, title, dial, bands, ticks, bar, target, value, unit, caption, bandsKey: null, ticksKey: null };
}

function drawBands(g, bands) {
  g.replaceChildren();
  for (const [from, to, level] of bands) {
    if (to > from) svg('path', { class: level, d: arc(from, to, R + 10) }, g);
  }
}

function drawTicks(g, ticks) {
  g.replaceChildren();
  for (const [at, label] of ticks) {
    const [x1, y1] = point(at, R + 7);
    const [x2, y2] = point(at, R + 13);
    svg('line', { x1, y1, x2, y2 }, g);
    const [x, y] = point(at, R + 20);
    const side = Math.cos(Math.PI * (1 - at));
    const anchor = side > 0.3 ? 'start' : side < -0.3 ? 'end' : 'middle';
    svg('text', { x, y, 'text-anchor': anchor, 'dominant-baseline': 'middle' }, g).textContent = label;
  }
}

export default function ({ data, parentElement }) {
  const g = parentElement.__labGauge || (parentElement.__labGauge = build(parentElement));

  g.title.textContent = data.title;
  g.dial.setAttribute('aria-label', `${data.title}: ${data.text} ${data.unit}`);
  g.value.textContent = data.text;
  g.unit.textContent = data.unit;
  g.caption.textContent = data.caption || ' '; // keep the line, and the height
  g.box.dataset.level = data.level;

  const bandsKey = JSON.stringify(data.bands);
  if (bandsKey !== g.bandsKey) { drawBands(g.bands, data.bands); g.bandsKey = bandsKey; }
  const ticksKey = JSON.stringify(data.ticks);
  if (ticksKey !== g.ticksKey) { drawTicks(g.ticks, data.ticks); g.ticksKey = ticksKey; }

  g.bar.style.strokeDasharray = `${data.value * 100} 100`;
  g.target.style.display = data.target === null ? 'none' : '';
  if (data.target !== null) g.target.style.transform = `rotate(${data.target * 180}deg)`;
  // Animate changes, but not the first placement.
  if (!g.box.classList.contains('ready')) requestAnimationFrame(() => g.box.classList.add('ready'));
}
