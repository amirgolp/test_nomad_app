// Follows the colour mode of the NOMAD GUI embedding this page; see
// nomad_embed.py. Runs once per page load.
const THEME_OPTIONS = ['light_theme', 'dark_theme'];
const POLL_MS = 1000;

const luminanceMode = (colour) => {
  const [r, g, b, a = 1] = (colour.match(/[\d.]+/g) || []).map(Number);
  if (r === undefined || a === 0) return null;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128 ? 'dark' : 'light';
};

const currentMode = () => {
  const app = document.querySelector('[data-testid="stApp"]') || document.body;
  return luminanceMode(getComputedStyle(app).backgroundColor);
};

// The GUI's mode, read from the embedding page. Only possible when the GUI is
// served from the same origin as NOMAD's API, as in a deployed Oasis.
const parentMode = () => {
  try {
    const doc = window.parent.document;
    const scheme = getComputedStyle(doc.documentElement).colorScheme;
    if (scheme === 'dark' || scheme === 'light') return scheme;
    return luminanceMode(getComputedStyle(doc.body).backgroundColor);
  } catch (error) {
    return null; // cross-origin
  }
};

// Streamlit picks its theme when the page loads; reload with the wanted one.
const follow = (mode) => {
  if (mode !== 'light' && mode !== 'dark') return;
  const url = new URL(window.location.href);
  const wanted = `${mode}_theme`;
  const options = url.searchParams.getAll('embed_options');
  // Already reloaded for this mode: never loop, even if the theme lacks it.
  if (mode === currentMode() || options.includes(wanted)) return;
  url.searchParams.delete('embed_options');
  for (const option of options) {
    if (!THEME_OPTIONS.includes(option)) url.searchParams.append('embed_options', option);
  }
  url.searchParams.append('embed_options', wanted);
  window.location.replace(url.toString());
};

export default function () {
  if (window.__labNomadEmbed || window.parent === window) return;
  window.__labNomadEmbed = true;

  if (parentMode() !== null) {
    // Same origin: watch the GUI directly, it switches without a reload.
    let last = null;
    const check = () => {
      const mode = parentMode();
      if (mode !== last) { last = mode; follow(mode); }
    };
    check();
    setInterval(check, POLL_MS);
    return;
  }

  // Cross-origin: only the GUI can tell, if it posts its mode.
  window.addEventListener('message', (event) => {
    const message = event.data;
    if (event.source !== window.parent || !message || message.type !== 'nomad:color-mode') return;
    follow(message.mode);
  });
  window.parent.postMessage({ type: 'nomad:color-mode-request' }, '*');
}
