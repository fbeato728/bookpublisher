'use strict';

// ── Monaco editor initialisation ─────────────────────────────────────────────
// Depends on: monacoReady (globals.js), window.monacoFailed (set by loader onerror)

function initMonaco(cb) {
  if (monacoReady) { cb(); return; }
  if (window.monacoFailed) { cb(new Error('Monaco not available')); return; }
  require.config({ paths: { vs: window.monacoBase } });
  require(['vs/editor/editor.main'], () => { monacoReady = true; cb(); });
}
