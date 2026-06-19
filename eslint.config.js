// Flat ESLint config for the web UI ES modules and their tests. The modules
// are dependency-free browser ESM (no build step); the tests run under
// node:test + jsdom (setup.mjs installs the DOM globals).
import js from '@eslint/js';

const browserGlobals = {
  document: 'readonly', window: 'readonly', navigator: 'readonly',
  fetch: 'readonly', Audio: 'readonly', console: 'readonly',
  setInterval: 'readonly', clearInterval: 'readonly',
  setTimeout: 'readonly', clearTimeout: 'readonly',
  structuredClone: 'readonly', getComputedStyle: 'readonly',
  HTMLElement: 'readonly', Element: 'readonly', Node: 'readonly',
  Event: 'readonly', CustomEvent: 'readonly',
};

export default [
  js.configs.recommended,
  {
    files: ['aibutton/web/static/**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: browserGlobals,
    },
  },
  {
    files: ['tests_js/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...browserGlobals, globalThis: 'writable', process: 'readonly' },
    },
  },
];
