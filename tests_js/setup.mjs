// Preloaded via `node --test --import ./tests_js/setup.mjs` so a DOM exists
// before the web ES modules are imported. The modules build nodes with
// document.createElement and wire DOM events; jsdom provides all of that.

import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
});

globalThis.window = dom.window;
globalThis.document = dom.window.document;

// The handful of constructors/classes the modules touch by name.
for (const name of [
  'Event', 'CustomEvent', 'HTMLElement', 'Element', 'Node', 'getComputedStyle',
]) {
  globalThis[name] = dom.window[name];
}

/** Fire a DOM event the way a user edit would (input/change). */
export function fire(node, type) {
  node.dispatchEvent(new dom.window.Event(type, { bubbles: true }));
}
