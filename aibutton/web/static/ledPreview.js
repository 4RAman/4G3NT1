// Renders an LED effect onto a DOM element - the browser's copy of what the
// ESP32's led.py does to a WS2812.
//
// This is the third implementation of the same six styles (firmware, here,
// and the palette that describes them), so it deliberately mirrors led.py
// step for step: the same triangle-wave breathe, the same half-period flash,
// the same hue rotation. If you change one, change the other - a preview that
// disagrees with the hardware is worse than no preview.
//
// One shared requestAnimationFrame ticker drives every registered element, so
// eight swatches in the palette editor plus the virtual device cost one loop,
// and it stops itself when nothing is registered.

// element -> { effect, mounted }. Callers paint swatches while building a
// subtree, before it is attached, so "not in the document" cannot by itself
// mean "discard this": a node is dropped only once it has been in the
// document and then left it, which is the re-render case the cleanup exists
// for. (rAF callbacks run after the current task, so in practice a node is
// attached by the first frame - this just doesn't depend on that.)
const painted = new Map();
let ticking = false;

function hsvToRgb(hue, sat, val) {
  const i = Math.floor(hue * 6);
  const f = hue * 6 - i;
  const p = val * (1 - sat);
  const q = val * (1 - sat * f);
  const t = val * (1 - sat * (1 - f));
  switch (i % 6) {
    case 0: return [val, t, p];
    case 1: return [q, val, p];
    case 2: return [p, val, t];
    case 3: return [p, q, val];
    case 4: return [t, p, val];
    default: return [val, p, q];
  }
}

function hexToRgb(hex) {
  const text = String(hex || '').replace('#', '');
  if (text.length !== 6) return [0, 0, 0];
  return [
    parseInt(text.slice(0, 2), 16) / 255,
    parseInt(text.slice(2, 4), 16) / 255,
    parseInt(text.slice(4, 6), 16) / 255,
  ];
}

const css = ([r, g, b]) =>
  `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;

/** The colour an effect shows at time `t` seconds. Mirrors firmware/led.py. */
export function colorAt(effect, t) {
  const period = Number(effect.period_s) > 0 ? Number(effect.period_s) : 1;
  const phase = (t % period) / period;
  switch (effect.style) {
    case 'breathe': {
      const level = phase < 0.5 ? 2 * phase : 2 * (1 - phase);
      return hexToRgb(effect.color).map((c) => c * level);
    }
    case 'flash':
      return phase < 0.5 ? hexToRgb(effect.color) : [0, 0, 0];
    case 'alternate':
      return phase < 0.5 ? hexToRgb(effect.color) : hexToRgb(effect.color2);
    case 'fade': {
      const level = phase < 0.5 ? 2 * phase : 2 * (1 - phase);
      const to = hexToRgb(effect.color2);
      return hexToRgb(effect.color).map((c, i) => c + (to[i] - c) * level);
    }
    case 'rainbow':
      return hsvToRgb(phase, 1, 1);
    default: // solid
      return hexToRgb(effect.color);
  }
}

function frame(now) {
  const t = now / 1000;
  for (const [node, entry] of painted) {
    if (node.isConnected) entry.mounted = true;
    else if (entry.mounted) { painted.delete(node); continue; }
    const { effect } = entry;
    const rgb = colorAt(effect, t);
    const color = css(rgb);
    node.style.background = color;
    // A little bloom, so a dim breathe reads as dim rather than as grey.
    const brightness = (rgb[0] + rgb[1] + rgb[2]) / 3;
    node.style.boxShadow = brightness > 0.05
      ? `0 0 ${Math.round(6 + brightness * 18)}px ${color}` : 'none';
  }
  if (painted.size) requestAnimationFrame(frame);
  else ticking = false;
}

/** Start (or update) the animation on `node`. */
export function paint(node, effect) {
  const existing = painted.get(node);
  painted.set(node, { effect, mounted: existing ? existing.mounted : false });
  if (!ticking) {
    ticking = true;
    requestAnimationFrame(frame);
  }
}

export function unpaint(node) {
  painted.delete(node);
}
