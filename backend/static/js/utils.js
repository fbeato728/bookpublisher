'use strict';

// ── Shared UI helpers ────────────────────────────────────────────────────────

function showStatus(id, msg, type) {
  document.getElementById(id).innerHTML = msg ? `<div class="status ${type}">${msg}</div>` : '';
}

function setEditorStatus(msg, type) {
  const el = document.getElementById('editor-status');
  el.textContent = msg;
  el.className = 'editor-status ' + type;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
