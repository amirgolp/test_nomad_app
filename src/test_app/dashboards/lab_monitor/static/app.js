// The Lab Monitor page. Polls the JSON API of the visible tab and hands the
// data to the instruments, which update their DOM in place. All URLs are
// relative, so the page works under any mount path (it is served at
// .../dashboards/lab-monitor/).
import annunciator from './annunciator.js';
import gauge from './gauge.js';
import ruptureFx from './rupture_fx.js';
import trends from './trends.js';

const $ = (id) => document.getElementById(id);

// The Oasis statistics change slowly; poll them at most every 5 s.
const OASIS_MIN_INTERVAL_S = 5;
// While a rupture can happen, poll every second so cancelling the countdown
// reaches every viewer quickly.
const AT_RISK_INTERVAL_S = 1;
const THEME_POLL_MS = 1000;

const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* ignore */ } },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
    ...options,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

// --- Theme ----------------------------------------------------------------
// Follows the GUI's colour mode when embedded on the same origin as NOMAD, as
// in a deployed Oasis. A GUI on another origin (e.g. the Vite dev server)
// cannot be read; the page then follows the system setting, as the GUI does by
// default.

const luminanceMode = (colour) => {
  const [r, g, b, a = 1] = (colour.match(/[\d.]+/g) || []).map(Number);
  if (r === undefined || a === 0) return null;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128 ? 'dark' : 'light';
};

function parentMode() {
  try {
    const root = window.parent.document.documentElement;
    const style = window.parent.getComputedStyle(root);
    const scheme = style.colorScheme;
    if (scheme === 'dark' || scheme === 'light') return scheme;
    const paper = style.getPropertyValue('--mui-palette-background-paper').trim();
    return luminanceMode(paper.startsWith('#') ? hexToRgb(paper) : paper)
      || luminanceMode(window.parent.getComputedStyle(window.parent.document.body).backgroundColor);
  } catch {
    return null; // cross-origin
  }
}

function hexToRgb(hex) {
  const value = hex.slice(1);
  const full = value.length === 3 ? [...value].map((c) => c + c).join('') : value.slice(0, 6);
  const n = parseInt(full, 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

function followGuiTheme() {
  if (window.parent === window) return;
  const apply = () => {
    const mode = parentMode();
    if (mode) document.documentElement.dataset.theme = mode;
    else delete document.documentElement.dataset.theme;
  };
  apply();
  if (parentMode() !== null) setInterval(apply, THEME_POLL_MS);
}

// --- Rendering ------------------------------------------------------------

const gaugeClass = (key) => `lab-gauge-${key}`;

// One slot per gauge key, kept across refreshes, so the gauges animate.
function renderGauges(container, gauges) {
  for (const data of gauges) {
    let slot = container.querySelector(`:scope > .${gaugeClass(data.key)}`);
    if (!slot) {
      slot = document.createElement('div');
      slot.className = gaugeClass(data.key);
      container.appendChild(slot);
    }
    gauge({ data, parentElement: slot });
  }
}

function renderMetrics(container, metrics) {
  container.hidden = metrics.length === 0;
  while (container.children.length < metrics.length) {
    const tile = document.createElement('div');
    tile.className = 'metric';
    tile.innerHTML = '<div class="label"><span class="name"></span></div><div class="value"></div>';
    container.appendChild(tile);
  }
  while (container.children.length > metrics.length) container.lastChild.remove();
  metrics.forEach((metric, i) => {
    const tile = container.children[i];
    tile.querySelector('.name').textContent = metric.label;
    tile.querySelector('.value').textContent = metric.value;
    let help = tile.querySelector('.help');
    if (metric.help && !help) {
      help = document.createElement('span');
      help.className = 'help';
      help.textContent = '?';
      help.tabIndex = 0;
      tile.querySelector('.label').appendChild(help);
    } else if (!metric.help && help) {
      help.remove();
      help = null;
    }
    if (help) {
      help.title = metric.help;
      help.setAttribute('aria-label', metric.help);
    }
  });
}

const controlsForm = $('controls');
const controlInputs = [...controlsForm.querySelectorAll('[data-control]')];
// Controls being dragged, or with a change on its way to the server; polls
// don't overwrite them.
const pending = new Set();

function showSliderValue(input) {
  const output = controlsForm.querySelector(`output[data-for="${input.dataset.control}"]`);
  if (output) output.textContent = `${Number(input.value).toFixed(0)} ${input.dataset.unit}`;
}

// The lab is shared: show the controls as they are on the server, unless the
// viewer is changing one right now.
function syncControls(controls) {
  for (const input of controlInputs) {
    const name = input.dataset.control;
    if (!(name in controls) || pending.has(name)) continue;
    if (input.type === 'checkbox') input.checked = controls[name];
    else input.value = controls[name];
    if (input.type === 'range') showSliderValue(input);
  }
}

function renderLab(view) {
  annunciator({ data: { tiles: view.alarms }, parentElement: $('lab-alarms') });
  renderGauges($('lab-gauges'), view.gauges);
  ruptureFx({ data: { ...view.rupture, anchor_class: gaugeClass(view.pressure_gauge) } });
  trends({ data: view.trends, parentElement: $('lab-trends') });
  $('overpressure').textContent = view.overpressure;
  syncControls(view.controls);
}

function renderOasis(view) {
  renderGauges($('oasis-gauges'), view.gauges);
  renderMetrics($('oasis-process-metrics'), view.process_metrics);
  renderMetrics($('oasis-content-metrics'), view.content_metrics);
  $('oasis-content-error').hidden = !view.content_error;
  $('oasis-content-error').textContent = view.content_error || '';
  $('oasis-version').textContent = view.version || '';
  trends({ data: view.trends, parentElement: $('oasis-trends') });
}

// --- Polling --------------------------------------------------------------

const refreshSelect = $('refresh');
const savedRefresh = storage.get('lab-monitor.refresh');
if (savedRefresh && [...refreshSelect.options].some((o) => o.value === savedRefresh)) {
  refreshSelect.value = savedRefresh;
}
const refreshSeconds = () => Number(refreshSelect.value);

function setStatus(error) {
  const status = $('status');
  status.dataset.state = error ? 'error' : 'ok';
  status.textContent = error
    ? 'Connection lost, retrying…'
    : `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
}

const tabs = {
  lab: { path: 'api/lab', render: renderLab, interval: (view) => (view?.at_risk ? AT_RISK_INTERVAL_S : refreshSeconds()) },
  oasis: { path: 'api/oasis', render: renderOasis, interval: () => Math.max(refreshSeconds(), OASIS_MIN_INTERVAL_S) },
};
let activeTab = storage.get('lab-monitor.tab') in tabs ? storage.get('lab-monitor.tab') : 'lab';
let timer = null;
let generation = 0; // Responses of a superseded poll are dropped.

async function poll() {
  clearTimeout(timer);
  timer = null;
  const tab = tabs[activeTab];
  const current = ++generation;
  let view = null;
  try {
    view = await api(tab.path);
    if (current !== generation) return;
    tab.render(view);
    setStatus(null);
  } catch (error) {
    if (current !== generation) return;
    console.error('Lab Monitor:', error);
    setStatus(error);
  }
  if (!document.hidden) timer = setTimeout(poll, tab.interval(view) * 1000);
}

// Renders a response to a change right away and restarts the polling clock.
function applyLabView(view) {
  generation++;
  renderLab(view);
  setStatus(null);
  clearTimeout(timer);
  timer = setTimeout(poll, tabs.lab.interval(view) * 1000);
}

const sending = new Set();

async function sendControl(name, value) {
  pending.add(name);
  sending.add(name);
  try {
    const view = await api('api/lab/controls', { method: 'PATCH', body: JSON.stringify({ [name]: value }) });
    pending.delete(name);
    applyLabView(view);
  } catch (error) {
    console.error('Lab Monitor:', error);
    setStatus(error);
  } finally {
    pending.delete(name);
    sending.delete(name);
  }
}

function selectTab(name) {
  activeTab = name;
  storage.set('lab-monitor.tab', name);
  for (const [key] of Object.entries(tabs)) {
    const button = $(`tab-${key}`);
    const selected = key === name;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(`panel-${key}`).hidden = !selected;
  }
  poll();
}

// --- Wiring ---------------------------------------------------------------

for (const input of controlInputs) {
  if (input.type === 'range') {
    input.addEventListener('input', () => showSliderValue(input));
    input.addEventListener('pointerdown', () => pending.add(input.dataset.control));
    // A release without a change sends nothing; stop holding the slider then.
    input.addEventListener('pointerup', () => setTimeout(() => {
      if (!sending.has(input.dataset.control)) pending.delete(input.dataset.control);
    }));
  }
  input.addEventListener('change', () => {
    sendControl(input.dataset.control, input.type === 'checkbox' ? input.checked : Number(input.value));
  });
}

$('reset').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    applyLabView(await api('api/lab/reset', { method: 'POST' }));
  } catch (error) {
    console.error('Lab Monitor:', error);
    setStatus(error);
  } finally {
    button.disabled = false;
  }
});

refreshSelect.addEventListener('change', () => {
  storage.set('lab-monitor.refresh', refreshSelect.value);
  poll();
});

const tabButtons = Object.keys(tabs).map((key) => $(`tab-${key}`));
tabButtons.forEach((button, i) => {
  const key = Object.keys(tabs)[i];
  button.addEventListener('click', () => selectTab(key));
  button.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    const next = tabButtons[(i + (event.key === 'ArrowRight' ? 1 : tabButtons.length - 1)) % tabButtons.length];
    next.focus();
    next.click();
  });
});

// No polling while the page is not visible; catch up when it is again.
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearTimeout(timer);
    timer = null;
  } else {
    poll();
  }
});

followGuiTheme();
selectTab(activeTab);
