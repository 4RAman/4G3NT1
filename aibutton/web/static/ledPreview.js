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

/** `level` 0..1 through a fade curve. The browser twin of `sequencer.shape`;
 *  an unknown curve is linear there and here, for the same reason - a look
 *  that renders plainly beats one that throws. */
function shape(curve, level) {
  if (level <= 0) return 0;
  if (level >= 1) return 1;
  switch (curve) {
    case 'ease_in': return level * level;
    case 'ease_out': return 1 - (1 - level) ** 2;
    case 'ease_in_out':
      return level < 0.5 ? 2 * level * level : 1 - 2 * (1 - level) ** 2;
    // _EXP_K in sequencer.py. Kept as the literal it is on both sides: the
    // number is the shape, and naming it here would not make the two any
    // harder to change apart.
    case 'exponential': return Math.expm1(4 * level) / Math.expm1(4);
    default: return level;
  }
}

/** The colour an effect shows at time `t` seconds. Mirrors firmware/led.py. */
export function colorAt(effect, t) {
  // A stop list (TODO 19b) - the browser twin of sequencer.plan_at, and it
  // keeps that module's honesty rules: fades are quantised to the same 50 ms
  // steps the host actually pushes over the radio, and the first instant of
  // a fade shows the untouched starting colour. One deliberate difference:
  // a one-shot previews looping, because a swatch that goes dark after one
  // pass looks broken - what a one-shot does at its end is the driver's
  // business, not the preview's.
  if (Array.isArray(effect.stops) && effect.stops.length) {
    const stops = effect.stops;
    const spans = stops.map((s) => [
      Math.max(Number(s.fade_s) || 0, 0), Math.max(Number(s.hold_s) || 0, 0),
    ]);
    const total = spans.reduce((sum, [fade, hold]) => sum + fade + hold, 0);
    let prev = stops[stops.length - 1].color;
    if (total <= 0) return hexToRgb(prev);
    let tt = t % total;
    for (let i = 0; i < stops.length; i += 1) {
      const [fade, hold] = spans[i];
      if (tt < fade) {
        const stepped = Math.min(Math.floor(tt / 0.05) * 0.05 / fade, 1);
        const level = shape(stops[i].curve, stepped);
        const from = hexToRgb(prev);
        const to = hexToRgb(stops[i].color);
        return from.map((c, j) => c + (to[j] - c) * level);
      }
      // A stop may animate during its hold (TODO 36c). Recursing into the
      // plain-effect half below is what keeps "flashing yellow" look identical
      // whether it is a stop in a list or a look on its own - and the phase is
      // measured from the stop's own start, so the movement begins when the
      // stop does rather than wherever the sequence's clock happens to be.
      if (tt < fade + hold) {
        const stop = stops[i];
        if (stop.style && stop.style !== 'solid') {
          return colorAt(
            { style: stop.style, color: stop.color, color2: '#000000',
              period_s: stop.period_s },
            tt - fade,
          );
        }
        return hexToRgb(stop.color);
      }
      tt -= fade + hold;
      prev = stops[i].color;
    }
    return hexToRgb(prev);
  }
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
