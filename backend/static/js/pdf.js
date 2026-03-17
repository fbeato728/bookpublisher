'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let pdfConfig       = null;
let pdfSelectedEpub = null;  // currently selected EPUB filename

// ── Load panel ────────────────────────────────────────────────────────────────
async function loadPdfPanel() {
  if (!currentProject) return;
  document.getElementById('pdf-project-badge').textContent = currentProject.id;
  await Promise.all([
    loadPdfConfig(),
    loadPdfEpubList(),
  ]);
}

// ── Config ────────────────────────────────────────────────────────────────────
async function loadPdfConfig() {
  try {
    pdfConfig = await apiFetch('GET', `/projects/${currentProject.id}/pdf-config`);
    _populatePdfForm(pdfConfig);
    renderPdfHistory(pdfConfig.history || []);
  } catch(e) {
    console.error('loadPdfConfig:', e);
  }
}

function _populatePdfForm(cfg) {
  const p = cfg.page        || {};
  const t = cfg.typography  || {};
  const c = cfg.conversion  || {};

  document.getElementById('pdf-page-width').value     = p.width           || '';
  document.getElementById('pdf-page-height').value    = p.height          || '';
  document.getElementById('pdf-margin-top').value     = p.margin_top      || '';
  document.getElementById('pdf-margin-bottom').value  = p.margin_bottom   || '';
  document.getElementById('pdf-margin-inside').value  = p.margin_inside   || '';
  document.getElementById('pdf-margin-outside').value = p.margin_outside  || '';

  document.getElementById('pdf-font-size').value      = t.font_size             || '';
  document.getElementById('pdf-counter-offset').value = t.page_counter_offset ?? '';
  document.getElementById('pdf-chapter-break').value  = t.chapter_break        || 'right';

  document.getElementById('pdf-trim').checked        = !!c.trim;
  document.getElementById('pdf-trim-start').value    = c.trim_start ?? '';
  document.getElementById('pdf-trim-end').value      = c.trim_end   ?? '';
  document.getElementById('pdf-keep-prince').checked = !!c.keep_prince_pdf;
}

function _collectPdfForm() {
  return {
    page: {
      width:          document.getElementById('pdf-page-width').value.trim(),
      height:         document.getElementById('pdf-page-height').value.trim(),
      margin_top:     document.getElementById('pdf-margin-top').value.trim(),
      margin_bottom:  document.getElementById('pdf-margin-bottom').value.trim(),
      margin_inside:  document.getElementById('pdf-margin-inside').value.trim(),
      margin_outside: document.getElementById('pdf-margin-outside').value.trim(),
    },
    typography: {
      font_size:            document.getElementById('pdf-font-size').value.trim(),
      page_counter_offset:  parseInt(document.getElementById('pdf-counter-offset').value) || 0,
      chapter_break:        document.getElementById('pdf-chapter-break').value,
    },
    conversion: {
      trim:            document.getElementById('pdf-trim').checked,
      trim_start:      parseInt(document.getElementById('pdf-trim-start').value) || 0,
      trim_end:        parseInt(document.getElementById('pdf-trim-end').value)   || 0,
      keep_prince_pdf: document.getElementById('pdf-keep-prince').checked,
    },
  };
}

async function savePdfConfig() {
  if (!currentProject) return;
  const data = _collectPdfForm();
  try {
    const res = await apiFetch('POST', `/projects/${currentProject.id}/pdf-config`, data);
    pdfConfig = res.config;
    showStatus('pdf-action-status', '✓ Settings saved', 'ok');
  } catch(e) {
    showStatus('pdf-action-status', '✗ ' + e.message, 'err');
  }
}

// ── EPUB list ─────────────────────────────────────────────────────────────────
async function loadPdfEpubList() {
  const list = document.getElementById('pdf-epub-list');
  try {
    const epubs = await apiFetch('GET', `/projects/${currentProject.id}/print-epubs`);
    list.innerHTML = '';
    if (!epubs.length) {
      list.innerHTML = '<div style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">No print EPUBs found.</div>';
      pdfSelectedEpub = null;
      return;
    }
    // Newest first
    epubs.slice().reverse().forEach((fname, idx) => {
      const el = document.createElement('div');
      el.className = 'pdf-epub-item';
      el.textContent = fname;
      el.dataset.filename = fname;
      el.addEventListener('click', () => selectPdfEpub(fname));
      list.appendChild(el);
      // Auto-select the first (newest)
      if (idx === 0) selectPdfEpub(fname);
    });
  } catch(e) {
    list.innerHTML = `<div style="font-family:var(--mono);font-size:0.72rem;color:var(--accent)">${escHtml(e.message)}</div>`;
  }
}

function selectPdfEpub(fname) {
  pdfSelectedEpub = fname;
  document.querySelectorAll('.pdf-epub-item').forEach(el => {
    el.classList.toggle('active', el.dataset.filename === fname);
  });
}

// ── Convert ───────────────────────────────────────────────────────────────────
async function convertToPdf() {
  if (!currentProject) return;
  if (!pdfSelectedEpub) {
    showStatus('pdf-action-status', '✗ Select a print EPUB first', 'err'); return;
  }

  const btn = document.getElementById('btn-pdf-convert');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Converting…';
  showStatus('pdf-action-status', 'Converting…', 'info');
  document.getElementById('pdf-log-wrap').classList.add('hidden');

  // Save current form values first
  const formData = _collectPdfForm();
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/pdf-config`, formData);
  } catch(e) { /* non-fatal */ }

  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/convert-pdf`, {
      epub_filename: pdfSelectedEpub,
    });

    // Show log
    if (data.log) {
      document.getElementById('pdf-log').textContent = data.log;
      document.getElementById('pdf-log-wrap').classList.remove('hidden');
    }

    if (!data.ok) {
      showStatus('pdf-action-status', '✗ ' + (data.error || 'Conversion failed'), 'err');
      return;
    }

    showStatus('pdf-action-status', `✓ PDF ready: ${data.pdf_filename}`, 'ok');

    // Reload config to get updated history
    await loadPdfConfig();

    // Load PDF in viewer
    loadPdfViewer(data.pdf_filename);

  } catch(e) {
    showStatus('pdf-action-status', '✗ ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '⎙ Convert to PDF';
  }
}

// ── Viewer ────────────────────────────────────────────────────────────────────
function loadPdfViewer(filename) {
  const pdfUrl    = `/publisher/api/projects/${currentProject.id}/pdf/${encodeURIComponent(filename)}`;
  const viewerUrl = `/publisher/static/pdfjs/web/viewer.html?file=${encodeURIComponent(pdfUrl)}#spread=even&pagemode=bookmarks`;
  document.getElementById('pdf-viewer-frame').src = viewerUrl;
  document.getElementById('pdf-viewer-filename').textContent = filename;
}

// ── History ───────────────────────────────────────────────────────────────────
function renderPdfHistory(history) {
  const list = document.getElementById('pdf-history-list');
  if (!history.length) {
    list.innerHTML = '<div style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">No conversions yet.</div>';
    return;
  }
  list.innerHTML = '';
  // Newest first
  [...history].reverse().forEach(entry => {
    const ts   = entry.timestamp ? entry.timestamp.replace('T', ' ').slice(0, 16) : '';
    const trim = entry.trim_start || entry.trim_end
      ? ` · trim ${entry.trim_start}/${entry.trim_end}` : '';

    const row = document.createElement('div');
    row.className = 'pdf-history-item';
    row.innerHTML = `
      <div style="font-family:var(--mono);font-size:0.68rem;color:var(--text3);margin-bottom:0.2rem">${escHtml(ts)}${trim}</div>
      <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap">
        <span style="font-family:var(--mono);font-size:0.72rem;color:var(--text2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(entry.epub_version)}">${escHtml(entry.epub_version)}</span>
        <button class="btn" style="padding:0.15rem 0.4rem;font-size:0.68rem" onclick="loadPdfViewer('${escHtml(entry.pdf_filename)}')">⎙ PDF</button>
        ${entry.prince_pdf_filename ? `<button class="btn" style="padding:0.15rem 0.4rem;font-size:0.68rem" onclick="loadPdfViewer('${escHtml(entry.prince_pdf_filename)}')">⎙ Prince</button>` : ''}
      </div>
    `;
    list.appendChild(row);
  });
}

// ── Navigate from Build panel ─────────────────────────────────────────────────
function goToPdfTools() {
  showPanel('pdf');
}