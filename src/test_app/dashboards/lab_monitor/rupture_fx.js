export default function (component) {
  const { data, parentElement } = component;
  // The overlays live on <body>, outside the component: hand them the theme.
  const theme = getComputedStyle(parentElement);
  document.documentElement.style.setProperty('--lab-fx-bg', theme.getPropertyValue('--st-background-color').trim() || '#fff');
  document.documentElement.style.setProperty('--lab-fx-font', theme.getPropertyValue('--st-font').trim() || 'sans-serif');
  const fx = (window.__labRuptureFx ||= {
    deadline: null, played: null, lastSecond: null, countdown: null, stamp: null, raf: null, seen: 0,
  });
  fx.seen = performance.now();
  fx.total = data.countdown_seconds;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const anchorRect = () => {
    const anchor = document.querySelector('.' + data.anchor_class);
    const rect = anchor ? anchor.getBoundingClientRect() : null;
    // A gauge in an inactive tab has no size.
    return rect && rect.width > 0 && rect.height > 0 ? rect : null;
  };

  const place = (node, rect, size) => {
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height * 0.6; // centre of the gauge dial
    Object.assign(node.style, {
      left: (cx - size / 2) + 'px', top: (cy - size / 2) + 'px',
      width: size + 'px', height: size + 'px',
    });
  };

  const removeCountdown = () => {
    if (fx.countdown) fx.countdown.remove();
    fx.countdown = null;
    fx.deadline = null;
    fx.lastSecond = null;
  };
  const removeStamp = () => {
    if (fx.stamp) fx.stamp.remove();
    fx.stamp = null;
  };

  const showStamp = () => {
    if (fx.stamp) return;
    fx.stamp = document.createElement('div');
    fx.stamp.className = 'lab-fx lab-stamp';
    fx.stamp.innerHTML = '<span>RUPTURED</span>';
    document.body.appendChild(fx.stamp);
  };

  const explode = () => {
    const rect = anchorRect();
    if (!rect) { showStamp(); return; } // gauge not on screen: skip the animation
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height * 0.6;

    const flash = document.createElement('div');
    flash.className = 'lab-flash';
    flash.style.setProperty('--x', x + 'px');
    flash.style.setProperty('--y', y + 'px');
    document.body.appendChild(flash);
    setTimeout(() => flash.remove(), 1000);

    if (!reducedMotion) {
      const boom = document.createElement('div');
      boom.className = 'lab-boom';
      Object.assign(boom.style, { left: x + 'px', top: y + 'px' });
      boom.innerHTML = '<div class="smoke"></div><div class="fireball"></div>'
        + '<div class="shock"></div><div class="shock late"></div>';
      const colours = ['#ffca28', '#ff7043', '#e53935', '#8d6e63', '#9e9e9e', '#fff59d'];
      for (let i = 0; i < 36; i++) {
        const angle = Math.random() * Math.PI * 2;
        const distance = 120 + Math.random() * 320;
        const piece = document.createElement('div');
        piece.className = 'debris';
        piece.style.setProperty('--dx', Math.cos(angle) * distance + 'px');
        piece.style.setProperty('--dy', Math.sin(angle) * distance + 'px');
        piece.style.setProperty('--r', (Math.random() * 1080 - 540) + 'deg');
        piece.style.setProperty('--s', (4 + Math.random() * 9) + 'px');
        piece.style.setProperty('--t', (0.7 + Math.random() * 0.9) + 's');
        piece.style.setProperty('--c', colours[i % colours.length]);
        boom.appendChild(piece);
      }
      document.body.appendChild(boom);
      setTimeout(() => boom.remove(), 3000);

      const app = document.querySelector('[data-testid="stAppViewContainer"]') || document.body;
      app.classList.remove('lab-shake');
      void app.offsetWidth; // restart the animation
      app.classList.add('lab-shake');
      setTimeout(() => app.classList.remove('lab-shake'), 800);
    }
    setTimeout(showStamp, reducedMotion ? 0 : 450);
  };

  const showCountdown = () => {
    if (fx.countdown) return;
    fx.countdown = document.createElement('div');
    fx.countdown.className = 'lab-fx lab-countdown';
    fx.countdown.innerHTML = '<svg viewBox="0 0 100 100"><circle class="ring-bg" cx="50" cy="50" r="44" stroke-width="6"/>'
      + '<circle class="ring" cx="50" cy="50" r="44" stroke-width="6" transform="rotate(-90 50 50)"/></svg>'
      + '<div class="digits"></div><div class="caption">RUPTURE IN</div>';
    document.body.appendChild(fx.countdown);
  };

  const frame = () => {
    fx.raf = null;
    // The component stopped refreshing (page left, panel removed): clean up.
    if (performance.now() - fx.seen > 15000) { removeCountdown(); removeStamp(); return; }
    const rect = anchorRect();
    for (const node of [fx.countdown, fx.stamp]) {
      if (node) node.style.display = rect ? '' : 'none';
    }
    if (fx.countdown && fx.deadline !== null) {
      const remaining = Math.max(0, (fx.deadline - performance.now()) / 1000);
      if (rect) place(fx.countdown, rect, Math.min(140, rect.height * 0.66));
      const ring = fx.countdown.querySelector('.ring');
      const circumference = 2 * Math.PI * 44;
      ring.setAttribute('stroke-dasharray', circumference);
      ring.setAttribute('stroke-dashoffset', circumference * (1 - remaining / fx.total));
      const second = Math.ceil(remaining);
      if (second !== fx.lastSecond) {
        fx.lastSecond = second;
        fx.countdown.querySelector('.digits').textContent = second;
        fx.countdown.classList.toggle('final', second <= 3);
        fx.countdown.classList.remove('tick');
        void fx.countdown.offsetWidth;
        fx.countdown.classList.add('tick');
      }
      if (remaining <= 0) {
        // Final tick: explode now, the server confirms on its next refresh.
        removeCountdown();
        fx.played = 'local';
        explode();
      }
    }
    if (fx.stamp && rect) place(fx.stamp, rect, Math.min(220, rect.height));
    if (fx.countdown || fx.stamp) fx.raf = requestAnimationFrame(frame);
  };
  const schedule = () => { if (fx.raf === null) fx.raf = requestAnimationFrame(frame); };

  if (data.ruptured_at !== null) {
    removeCountdown();
    // Explode for viewers who did not see the countdown end, but not for
    // someone opening the page long after the rupture.
    if (fx.played !== 'local' && fx.played !== data.ruptured_at && data.ruptured_age < 10) {
      explode();
    } else {
      showStamp();
    }
    fx.played = data.ruptured_at;
  } else {
    removeStamp();
    if (data.remaining !== null && fx.played === 'local' && data.remaining < 1.5) {
      // Exploded locally; the server is a step behind and confirms shortly.
    } else if (data.remaining !== null) {
      fx.played = null;
      fx.deadline = performance.now() + data.remaining * 1000;
      showCountdown();
    } else {
      removeCountdown();
      fx.played = null;
    }
  }
  schedule();
}
