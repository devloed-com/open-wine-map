// Flat ESLint config for the map application source.
//
// scripts/_lib/assets/app.js is a real, lint-able JS file (extracted from the
// Python template in Phase 4). Build-time per-locale values are injected by
// `_render_app_js` in scripts/_lib/map_template.py via `__OWM_<slot>__`
// tokens that sit exactly where the old `{slot}` format fields were — so those
// identifiers are declared as globals here (the runtime/emitted file never
// contains them). Lint is advisory: it does NOT gate the build (the byte-
// identity golden check does). Run with: npx --yes eslint@9
const fs = require("node:fs");
const path = require("node:path");

const appJs = fs.readFileSync(
  path.join(__dirname, "scripts/_lib/assets/app.js"),
  "utf8",
);
const owmTokens = Object.fromEntries(
  [...new Set(appJs.match(/__OWM_\w+?__/g) || [])].map((t) => [t, "readonly"]),
);

const browserGlobals = {
  window: "readonly",
  document: "readonly",
  navigator: "readonly",
  location: "readonly",
  localStorage: "readonly",
  history: "readonly",
  fetch: "readonly",
  console: "readonly",
  setTimeout: "readonly",
  clearTimeout: "readonly",
  requestAnimationFrame: "readonly",
  getComputedStyle: "readonly",
  URLSearchParams: "readonly",
  URL: "readonly",
  CSS: "readonly",
  Event: "readonly",
  CustomEvent: "readonly",
  MutationObserver: "readonly",
  // vendored runtime libraries (self-hosted under /assets/vendor/)
  maplibregl: "readonly",
  pmtiles: "readonly",
};

module.exports = [
  {
    files: ["scripts/_lib/assets/app.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...browserGlobals, ...owmTokens },
    },
    rules: {
      "no-undef": "error",
      // Advisory only. `caughtErrors: none` ignores the many intentional
      // `catch (e) {}` swallows; `argsIgnorePattern` ignores `(_, k) =>`
      // throwaway args. The remaining unused-var warnings are pre-existing in
      // the extracted JS and left untouched (app.js must stay byte-identical
      // to the previous inline template — the build is verified on that).
      "no-unused-vars": ["warn", { caughtErrors: "none", argsIgnorePattern: "^_" }],
    },
  },
];
