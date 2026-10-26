// Small line charts, one panel per quantity group. The panels are kept across
// refreshes; only their SVG content is redrawn, in a single frame, so the page
// does not flicker. Hovering shows the values at the nearest sample.
const HEIGHT = 190;
const PAD = { left: 48, right: 12, top: 8, bottom: 22 };

const niceStep = (span, count) => {
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const error = raw / magnitude;
  return (error >= 7.5 ? 10 : error >= 3.5 ? 5 : error >= 1.5 ? 2 : 1) * magnitude;
};

const formatNumber = (v) => {
  if (v === 0) return '0';
  const abs = Math.abs(v);
  if (abs >= 1e4 || abs < 1e-2) return v.toExponential(1).replace('e+', 'e');
  return String(+v.toPrecision(3));
};

const formatTime = (seconds, withSeconds = true) => new Date(seconds * 1000).toLocaleTimeString([], {
  hour: '2-digit', minute: '2-digit', ...(withSeconds ? { second: '2-digit' } : {}),
});

// The y axis of a panel: maps a value to [0, 1] and lists the gridlines.
function yAxis(panel) {
  const values = panel.series.flatMap((s) => s.values)
    .filter((v) => Number.isFinite(v) && (!panel.log || v > 0));
  if (panel.log) {
    const lo = values.length ? Math.floor(Math.log10(Math.min(...values))) : 0;
    let hi = values.length ? Math.ceil(Math.log10(Math.max(...values))) : 1;
    if (hi <= lo) hi = lo + 1;
    const every = Math.max(1, Math.ceil((hi - lo) / 5));
    const ticks = [];
    for (let e = lo; e <= hi; e += every) ticks.push({ at: (e - lo) / (hi - lo), label: `1e${e}` });
    return { ticks, scale: (v) => (v > 0 ? (Math.log10(v) - lo) / (hi - lo) : null) };
  }
  let lo = panel.min ?? (values.length ? Math.min(...values) : 0);
  let hi = panel.max ?? (values.length ? Math.max(...values) : 1);
  if (hi <= lo) { hi = lo + 1; lo -= panel.min === null ? 1 : 0; }
  const step = niceStep(hi - lo, 4);
  if (panel.min === null) lo = Math.floor(lo / step) * step;
  if (panel.max === null) hi = Math.ceil(hi / step) * step;
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    ticks.push({ at: (v - lo) / (hi - lo), label: formatNumber(+v.toPrecision(12)) });
  }
  return { ticks, scale: (v) => (Number.isFinite(v) ? (v - lo) / (hi - lo) : null) };
}

function palette(host) {
  const colours = getComputedStyle(host).getPropertyValue('--lab-chart-colors');
  return colours ? colours.split(',').map((c) => c.trim()) : ['#2A4CDF', '#008564', '#976D2B'];
}

function buildPanel() {
  const node = document.createElement('div');
  node.className = 'panel';
  node.innerHTML = '<div class="head"><span class="name"></span><span class="legend"></span></div>'
    + '<svg class="plot"></svg><div class="tooltip" hidden></div>';
  return node;
}

function render(state) {
  const { data, root, host } = state;
  const colours = palette(host);
  const times = data.times;
  const t0 = times[0], t1 = times[times.length - 1];
  const x = (t) => (t1 > t0 ? (t - t0) / (t1 - t0) : 1);

  while (root.children.length < data.panels.length) root.appendChild(buildPanel());
  while (root.children.length > data.panels.length) root.lastChild.remove();

  data.panels.forEach((panel, index) => {
    const node = root.children[index];
    const width = Math.max(node.clientWidth, 200);
    const plotW = width - PAD.left - PAD.right, plotH = HEIGHT - PAD.top - PAD.bottom;
    const axis = yAxis(panel);
    const px = (t) => PAD.left + x(t) * plotW;
    const py = (f) => PAD.top + (1 - f) * plotH;

    node.querySelector('.name').textContent = panel.title;
    node.querySelector('.legend').innerHTML = panel.series.map((s, i) => `<span class="key"><i style="background:${colours[i % colours.length]}"></i>${s.name}</span>`).join('');

    let content = '';
    for (const tick of axis.ticks) {
      const y = py(tick.at).toFixed(1);
      content += `<line class="grid" x1="${PAD.left}" x2="${width - PAD.right}" y1="${y}" y2="${y}"/>`
        + `<text class="ylabel" x="${PAD.left - 6}" y="${y}">${tick.label}</text>`;
    }
    if (t1 > t0) {
      for (let i = 0; i <= 3; i++) {
        const t = t0 + ((t1 - t0) * i) / 3;
        const anchor = i === 0 ? 'start' : i === 3 ? 'end' : 'middle';
        content += `<text class="xlabel" x="${px(t).toFixed(1)}" y="${HEIGHT - 6}" text-anchor="${anchor}">${formatTime(t)}</text>`;
      }
    }
    panel.series.forEach((s, i) => {
      let d = '';
      s.values.forEach((v, j) => {
        const f = axis.scale(v);
        if (f === null) return;
        d += `${d ? 'L' : 'M'}${px(times[j]).toFixed(1)} ${py(Math.min(1.05, Math.max(-0.05, f))).toFixed(1)}`;
      });
      content += `<path class="line" d="${d}" stroke="${colours[i % colours.length]}"/>`;
    });
    content += '<g class="cursor"></g>'
      + `<rect class="hover" x="${PAD.left}" y="${PAD.top}" width="${plotW}" height="${plotH}"/>`;

    const plot = node.querySelector('.plot');
    plot.setAttribute('viewBox', `0 0 ${width} ${HEIGHT}`);
    plot.setAttribute('height', HEIGHT);
    plot.innerHTML = content;

    const hover = plot.querySelector('.hover');
    const show = (fraction) => {
      state.hover = { index, fraction };
      const target = t0 + fraction * (t1 - t0);
      let j = 0;
      while (j < times.length - 1 && Math.abs(times[j + 1] - target) <= Math.abs(times[j] - target)) j++;
      const cx = px(times[j]);
      let cursor = `<line x1="${cx}" x2="${cx}" y1="${PAD.top}" y2="${PAD.top + plotH}"/>`;
      const rows = [`<b>${formatTime(times[j])}</b>`];
      panel.series.forEach((s, i) => {
        const f = axis.scale(s.values[j]);
        if (f !== null) cursor += `<circle cx="${cx}" cy="${py(Math.min(1, Math.max(0, f)))}" r="3" fill="${colours[i % colours.length]}"/>`;
        rows.push(`<span><i style="background:${colours[i % colours.length]}"></i>${s.name}: ${formatNumber(s.values[j])}</span>`);
      });
      plot.querySelector('.cursor').innerHTML = cursor;
      const tooltip = node.querySelector('.tooltip');
      tooltip.innerHTML = rows.join('');
      tooltip.hidden = false;
      tooltip.style.left = `${Math.min(cx + 10, width - tooltip.offsetWidth - 4)}px`;
    };
    hover.addEventListener('pointermove', (event) => {
      const box = hover.getBoundingClientRect();
      show(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)));
    });
    hover.addEventListener('pointerleave', () => {
      state.hover = null;
      plot.querySelector('.cursor').innerHTML = '';
      node.querySelector('.tooltip').hidden = true;
    });
    if (state.hover && state.hover.index === index) show(state.hover.fraction);
    else node.querySelector('.tooltip').hidden = true;
  });
}

export default function ({ data, parentElement }) {
  let state = parentElement.__labTrends;
  if (!state) {
    const root = document.createElement('div');
    root.className = 'trends';
    parentElement.appendChild(root);
    state = parentElement.__labTrends = { root, host: parentElement.host || parentElement, hover: null };
    let width = 0;
    new ResizeObserver(() => {
      if (root.clientWidth !== width && state.data) { width = root.clientWidth; render(state); }
    }).observe(root);
  }
  state.data = data;
  render(state);
}
