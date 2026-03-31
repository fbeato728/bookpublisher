'use strict';

// ── Navigation ───────────────────────────────────────────────────────────────
async function showPanel(name) {
  if (name !== 'editor' && isDirty && currentChapterFile) {
    const result = await confirmIfDirty();
    if (result === 'cancel') return;
  }
  if (name !== 'editor' && previewVisible) togglePreviewPane();
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  document.querySelector(`[data-panel="${name}"]`)?.classList.add('active');
  // document.getElementById('fs-control').style.display =
  //   (name === 'split' || name === 'editor') ? 'flex' : 'none';
  if (name === 'overview' && currentProject) {
    loadOverview();
    loadImageList();
    loadMetadataPanel();
    loadCssTokensPanel();
  }
  if (name === 'build' && currentProject) { 
    const preserveFile = buildPreviewFile;  // Save the currently previewed file
    buildConfig = null; 
    loadBuildConfig().then(() => {
      // After config reloads, restore the preview
      if (preserveFile && buildConfig) {
        const item = [...(buildConfig[buildProfile]?.front_matter || []),
                      ...(buildConfig[buildProfile]?.back_matter || [])].find(i => {
                        return i.filename === preserveFile || i.id === preserveFile;
                      });
        if (item) {
          previewBuildItem(item);
        } else {
        }
      } else {
      }
    });
    loadImageList(); 
    loadFootnotes(); 
  }
  if (name === 'split' && currentProject) { showSplitsView(); loadFullXhtml(); }
  if (name === 'editor' && currentProject) {
    loadChapterList(); loadIgnoreWords(); loadFootnotes();
    apiFetch('POST', `/projects/${currentProject.id}/css-tokens/sync`).catch(() => {});
  }
  if (name === 'pdf'    && currentProject) loadPdfPanel();
  if (monacoEditor) monacoEditor.layout();
}

// ── Projects ─────────────────────────────────────────────────────────────────
async function loadProjects() {
  try {
    const projects = await apiFetch('GET', '/projects');
    const list     = document.getElementById('project-list');
    list.innerHTML = '';
    projects.forEach(p => {
      const el = document.createElement('div');
      el.className  = 'project-item' + (currentProject?.id === p.id ? ' active' : '');
      el.textContent = p.id;  // ← change to this
      el.title = p.title || p.id;  // ← change to this
      el.dataset.projectId = p.id;
      el.onclick = () => openProject(p);
      list.appendChild(el);
    });
  } catch(e) { console.error('loadProjects:', e); }
}

async function openProject(p) {
  if (isDirty && currentChapterFile && currentProject?.id !== p.id) {
    const result = await confirmIfDirty();
    if (result === 'cancel') return;
  }
  if (currentProject?.id !== p.id) {
    // ── Split state ──────────────────────────────────────────────────────────
    splitSavedData = [];
    splitProjectId = null;
    splitMarkers   = [];

    // ── Editor state ─────────────────────────────────────────────────────────
    currentChapterFile = null;
    currentStylesheet  = '../styles/main.css';
    isDirty            = false;
    chaptersDirty      = false;
    chaptersEditing    = [];
    ltMatches          = [];
    ltCheckText        = '';
    cachedStyles       = {};
    fileIsHyphenated   = false;
    if (monacoEditor) {
      monacoLoading = true;
      monacoEditor.setValue('');
      monacoLoading = false;
    }
    document.getElementById('editor-filename').textContent = '— no file open —';
    document.getElementById('editor-content').innerHTML = '';
    document.getElementById('editor-content').dataset.rawXhtml = '';
    document.getElementById('preview-pane-body').innerHTML = '';
    setEditorStatus('', '');

    // ── Grammar ignore state ─────────────────────────────────────────────────
    ignoreWords = [];
    ignoreRules = [];

    // ── Footnote state ───────────────────────────────────────────────────────
    projectFootnotes   = [];
    projectFnVariants  = [];
    selectedFnVariant  = 'def';
    _fnMapCache        = null;
    _fnMapProjectId    = null;

    // ── Build state ──────────────────────────────────────────────────────────
    buildConfig      = null;
    buildPreviewFile = null;

    // ── PDF state ────────────────────────────────────────────────────────────
    pdfConfig       = null;
    pdfSelectedEpub = null;
    document.getElementById('pdf-viewer-frame').src = 'about:blank';
    document.getElementById('pdf-viewer-filename').textContent = 'no PDF loaded';
    document.getElementById('pdf-log-wrap').classList.add('hidden');
    document.getElementById('pdf-action-status').textContent = '';

    showSplitsView();
  }
  // Fetch fresh project data so metadata fields reflect latest meta.json
  try {
    const fresh = await apiFetch('GET', `/projects/${p.id}`);
    currentProject = fresh;
  } catch { currentProject = p; }
  document.getElementById('topbar-project').textContent = currentProject.id;
  document.getElementById('project-nav').classList.remove('hidden');
  document.querySelectorAll('.project-item').forEach(el =>
    el.classList.toggle('active', el.dataset.projectId === p.id)
  );
  // Sync CSS tokens active file on project open (fire-and-forget)
  await apiFetch('POST', `/projects/${currentProject.id}/css-tokens/sync`).catch(() => {});
  showPanel('overview');
}

// ── Upload mode tabs ─────────────────────────────────────────────────────────
function setUploadMode(mode) {
  uploadMode = mode;
  document.getElementById('tab-docx').classList.toggle('active', mode === 'docx');
  document.getElementById('tab-epub').classList.toggle('active', mode === 'epub');
  const fi = document.getElementById('file-input');
  fi.accept = mode === 'epub' ? '.epub' : '.docx,.odt';
  const ut  = document.getElementById('upload-text');
  ut.innerHTML = mode === 'epub'
    ? '<strong>Click to select an EPUB file</strong><br>or drag and drop here'
    : '<strong>Click to select a DOCX or ODT file</strong><br>or drag and drop here';
  document.getElementById('upload-area').querySelector('.upload-icon').textContent = mode === 'epub' ? '📚' : '📄';
}

// ── Upload ───────────────────────────────────────────────────────────────────
function onUploadAreaClick() { document.getElementById('file-input').click(); }
function onUploadDragover(e) { e.preventDefault(); document.getElementById('upload-area').classList.add('drag'); }
function onUploadDragleave() { document.getElementById('upload-area').classList.remove('drag'); }
function onUploadDrop(e) {
  e.preventDefault(); document.getElementById('upload-area').classList.remove('drag');
  if (e.dataTransfer.files[0]) {
    const f = e.dataTransfer.files[0];
    if (f.name.endsWith('.epub') && uploadMode !== 'epub') setUploadMode('epub');
    handleFile(f);
  }
}
function onFileInputChange() { const fi = document.getElementById('file-input'); if (fi.files[0]) handleFile(fi.files[0]); }

function handleFile(file) {
  document.getElementById('upload-text').innerHTML =
    `<strong>${file.name}</strong><br><span style="color:var(--text3)">${(file.size/1024).toFixed(0)} KB — ready to upload</span>`;
  const pid = document.getElementById('input-project-id');
  if (!pid.value) pid.value = file.name.replace(/\.[^.]+$/,'').toLowerCase().replace(/[^a-z0-9]/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'');
  const tit = document.getElementById('input-title');
  if (!tit.value) tit.value = file.name.replace(/\.[^.]+$/,'');
}

async function uploadManuscript() {
  const file      = document.getElementById('file-input').files[0];
  const projectId = document.getElementById('input-project-id').value.trim();
  const title     = document.getElementById('input-title').value.trim();
  const author    = document.getElementById('input-author').value.trim();

  if (!file)      { showStatus('upload-status', 'Please select a file', 'err'); return; }
  if (!projectId) { showStatus('upload-status', 'Please enter a Project ID', 'err'); return; }
  if (!title)     { showStatus('upload-status', 'Please enter a Book Title', 'err'); return; }

  const btn = document.getElementById('btn-upload');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> ' + (uploadMode === 'epub' ? 'Importing…' : 'Converting…');
  showStatus('upload-status', uploadMode === 'epub' ? 'Importing EPUB…' : 'Uploading and converting…', 'info');

  const form = new FormData();
  form.append('file', file); form.append('project_id', projectId);
  form.append('title', title); form.append('author', author);

  const path = uploadMode === 'epub' ? '/projects/import-epub' : '/projects';

  try {
    const data = await apiFetch('POST', path, form);
    const msg = uploadMode === 'epub'
      ? `✓ EPUB imported as "${data.id}" — ${(data.chapters||[]).length} chapters`
      : `✓ Project "${data.id}" created — "${data.title}"`;


    await loadProjects();
    openProject(data);
    // Reset upload form
    document.getElementById('file-input').value = '';
    document.getElementById('input-project-id').value = '';
    document.getElementById('input-title').value = '';
    document.getElementById('input-author').value = '';
    setUploadMode(uploadMode);
    showStatus('upload-status', '', '');    

  } catch(e) {
    showStatus('upload-status', '✗ Failed: ' + e.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = '↑ Upload & Convert';
  }
}

// ── Overview panel ───────────────────────────────────────────────────────────
// Renders only the #overview-info block from currentProject in memory —
// no API calls, runs synchronously. Called on metadata blur for instant
// feedback; loadOverview() still runs in background for the full panel.
function _renderOverviewInfo() {
  if (!currentProject) return;
  const info = document.getElementById('overview-info');
  if (!info) return;
  info.innerHTML = `
    <div><span style="color:var(--text3)">Project ID</span>&emsp;${currentProject.id}</div>
    <div><span style="color:var(--text3)">Title</span>&emsp;${escHtml(currentProject.title || '—')}</div>
    <div><span style="color:var(--text3)">Author</span>&emsp;${escHtml(currentProject.author || '—')}</div>
    <div><span style="color:var(--text3)">Status</span>&emsp;${escHtml(currentProject.status || '—')}</div>
  `;
}

async function loadOverview() {
  if (!currentProject) return;
  const info   = document.getElementById('overview-info');
  const status = document.getElementById('overview-status');
  const btn    = document.getElementById('btn-detect-footnotes');
  info.innerHTML = 'Loading…';
  try {
    let chapters = [], hasBuild = false, hasFootnotes = false, footnotesTotal = 0, footnotesInjected = false;
    try { chapters = await apiFetch('GET', `/projects/${currentProject.id}/chapters`); } catch {}
    try { await apiFetch('GET', `/projects/${currentProject.id}/build-config`); hasBuild = true; } catch {}
    try {
      const fnMap = await apiFetch('GET', `/projects/${currentProject.id}/footnotes/map`);
      hasFootnotes      = true;
      footnotesTotal    = fnMap.total || 0;
      footnotesInjected = fnMap.footnotes_injected || false;
    } catch {}

    info.innerHTML = `
      <div><span style="color:var(--text3)">Project ID</span>&emsp;${currentProject.id}</div>
      <div><span style="color:var(--text3)">Title</span>&emsp;${currentProject.title || '—'}</div>
      <div><span style="color:var(--text3)">Author</span>&emsp;${currentProject.author || '—'}</div>
      <div><span style="color:var(--text3)">Status</span>&emsp;${currentProject.status || '—'}</div>
      <div><span style="color:var(--text3)">full.xhtml</span>&emsp;✓</div>
      <div><span style="color:var(--text3)">Footnotes</span>&emsp;${hasFootnotes ? '✓' : '✗'}</div>
      <div><span style="color:var(--text3)">Chapters</span>&emsp;${chapters.length ? chapters.length + ' files' : '— none'}</div>
      <div><span style="color:var(--text3)">Build config</span>&emsp;${hasBuild ? '✓' : '—'}</div>
    `;

    const chaptersExist = chapters.length > 0;
    btn.disabled    = footnotesInjected || chaptersExist;
    btn.title       = (chaptersExist && !footnotesInjected)
      ? 'Chapters already exist — detection must run on full.xhtml before splitting'
      : '';
    btn.textContent = hasFootnotes ? '⎆ Re-detect Footnotes' : '⎆ Detect Footnotes';
    btn.dataset.hasFootnotes = hasFootnotes ? '1' : '';

    const injectBtn  = document.getElementById('btn-inject-footnotes');
    injectBtn.textContent = '⚡ Inject Footnotes';
    const results    = document.getElementById('overview-footnotes');
    const msg        = document.getElementById('overview-footnotes-msg');
    const resetBtn   = document.getElementById('btn-reset-footnotes');

    if (hasFootnotes) {
      const statusText = footnotesInjected ? ' — injected ✓' : '';
      msg.textContent       = `${footnotesTotal} footnote${footnotesTotal !== 1 ? 's' : ''} detected.${statusText}`;
      results.style.display = 'block';
      resetBtn.style.display  = 'inline-block';
      resetBtn.disabled       = chaptersExist;
      resetBtn.title          = chaptersExist ? 'Cannot reset footnotes while chapters exist' : '';
      injectBtn.style.display = footnotesInjected ? 'none' : 'inline-block';
      injectBtn.disabled      = false;

      // Audit
      const auditEl = document.getElementById('overview-footnotes-audit');
      try {
        const audit = await apiFetch('GET', `/projects/${currentProject.id}/footnotes/audit`);
        const n = audit.total_issues || 0;
        if (n === 0) {
          auditEl.textContent = '✓ No issues';
          auditEl.style.color = 'var(--ok)';
        } else {
          const lines = audit.issues.map(i => `#${i.display_num} ${i.type}: ${i.detail}`).join('\n');
          auditEl.textContent = `⚠ ${n} issue${n !== 1 ? 's' : ''}`;
          auditEl.title = lines;
          auditEl.style.color = 'var(--warn, var(--accent))';
        }
        auditEl.style.display = 'block';
      } catch { auditEl.style.display = 'none'; }
    } else {
      results.style.display   = 'none';
      resetBtn.style.display  = 'none';
      injectBtn.style.display = 'none';
    }

    status.innerHTML = '';
  } catch(e) {
    info.innerHTML = `<span style="color:var(--accent)">${e.message}</span>`;
  }
}

async function detectFootnotes() {
  if (!currentProject) return;
  const btn      = document.getElementById('btn-detect-footnotes');
  const results  = document.getElementById('overview-footnotes');
  const msg      = document.getElementById('overview-footnotes-msg');
  const resetBtn = document.getElementById('btn-reset-footnotes');
  const injectBtn = document.getElementById('btn-inject-footnotes');

  if (btn.dataset.hasFootnotes) {
    if (!confirm('Footnotes have already been detected for this project.\n\nRe-detecting will overwrite the existing data. Continue?')) return;
  }

  btn.disabled  = true;
  btn.innerHTML = '<span class="spinner"></span> Detecting…';
  results.style.display  = 'none';
  msg.textContent        = '';
  resetBtn.style.display = 'none';

  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/footnotes/detect`);
    const total = data.total || 0;
    if (total === 0) {
      msg.textContent         = 'No footnotes detected.';
      resetBtn.style.display  = 'none';
      injectBtn.style.display = 'none';
    } else {
      msg.textContent         = `${total} footnote${total !== 1 ? 's' : ''} detected.`;
      resetBtn.style.display  = 'inline-block';
      injectBtn.style.display = 'inline-block';
      injectBtn.disabled      = false;
    }
    results.style.display = 'block';
    await loadOverview();
  } catch(e) {
    const msg    = document.getElementById('overview-footnotes-msg');
    const results = document.getElementById('overview-footnotes');
    msg.textContent       = '✗ ' + e.message;
    results.style.display = 'block';
    btn.disabled          = false;
    btn.textContent       = btn.dataset.hasFootnotes ? '⎆ Re-detect Footnotes' : '⎆ Detect Footnotes';
  }
}

async function resetFootnotes() {
  if (!currentProject) return;
  if (!confirm('Reset footnotes for this project?\n\nThis will delete the detected footnotes map and restore the original full.xhtml. This cannot be undone.')) return;
  try {
    await apiFetch('DELETE', `/projects/${currentProject.id}/footnotes/map`);
    document.getElementById('overview-footnotes').style.display  = 'none';
    document.getElementById('overview-footnotes-msg').textContent = '';
    document.getElementById('btn-reset-footnotes').style.display = 'none';
    document.getElementById('btn-inject-footnotes').style.display = 'none';
    await loadOverview();
  } catch(e) {
    showStatus('overview-status', '✗ ' + e.message, 'err');
  }
}

async function injectFootnotes() {
  if (!currentProject) return;
  const btn       = document.getElementById('btn-inject-footnotes');
  const detectBtn = document.getElementById('btn-detect-footnotes');
  const msg       = document.getElementById('overview-footnotes-msg');

  btn.disabled       = true;
  btn.innerHTML      = '<span class="spinner"></span> Injecting…';
  detectBtn.disabled = true;

  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/footnotes/inject`);
    msg.textContent        = `${document.getElementById('overview-footnotes-msg').textContent.split('.')[0]}. Injected ✓ (${data.injected_count} paragraphs)`;
    btn.style.display      = 'none';
    detectBtn.disabled     = true;
    await loadOverview();
  } catch(e) {
    showStatus('overview-status', '✗ ' + e.message, 'err');
    btn.disabled      = false;
    btn.textContent   = '⚡ Inject Footnotes';
    detectBtn.disabled = false;
  }
}

async function deleteProject() {
  if (!currentProject) return;
  const id = currentProject.id;
  if (!confirm(`DELETE project "${id}" permanently?\n\nThis will remove all files including the original document. This cannot be undone.`)) return;
  if (!confirm(`Are you sure? "${id}" will be gone forever.`)) return;
  try {
    await apiFetch('DELETE', `/projects/${id}`);
    localStorage.removeItem('splits:' + id);
    currentProject = null;
    document.getElementById('project-nav').classList.add('hidden');
    await loadProjects();
    showPanel('welcome');
  } catch(e) { showStatus('overview-status', '✗ ' + e.message, 'err'); }
}

async function resetProject() {
  if (!currentProject) return;
  // if (!confirm(`Reset project "${currentProject.id}"?\n\nThis will delete all chapters, images, build config and footnotes, keeping only the original document and full.xhtml.`)) return;
  if (!confirm(`Reset project "${currentProject.id}"?\n\nThis will delete all chapter splits, keeping front/back matter, images, and the full converted manuscript (footnotes included if applicable).`)) return;
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/reset`);
    localStorage.removeItem('splits:' + currentProject.id);
    buildConfig              = null;
    currentProject.chapters  = [];
    currentProject.status    = 'converted'; // sync in-memory status — backend already wrote this to meta.json
    splitSavedData           = [];
    splitProjectId           = null;
    splitMarkers             = [];
    showStatus('overview-status', '✓ Project reset', 'ok');
    loadOverview();
  } catch(e) { showStatus('overview-status', '✗ ' + e.message, 'err'); }
}

// ── Metadata panel ────────────────────────────────────────────────────────────

async function loadMetadataPanel() {
  if (!currentProject) return;

  // Populate Group 1 — OPF fields always shown
  document.getElementById('build-title').value    = currentProject.title     || '';
  document.getElementById('build-author').value   = currentProject.author    || '';
  document.getElementById('build-language').value = currentProject.language  || 'ca';
  document.getElementById('build-publisher').value = currentProject.publisher || 'BonPort';

  // Fetch tokens definition and used tokens for this project
  const container = document.getElementById('metadata-fields');
  container.innerHTML = '';

  let tokenDefs = {};
  let usedTokens = [];
  try {
    [tokenDefs, usedTokens] = await Promise.all([
      apiFetch('GET', '/config/tokens'),
      apiFetch('GET', `/projects/${currentProject.id}/used-tokens`),
    ]);
  } catch(e) {
    console.error('loadMetadataPanel:', e);
    return;
  }

  // Group 1 tokens — skip, already rendered as static fields
  const GROUP1 = new Set(['title', 'author', 'language', 'publisher']);

  // Sort by order field — tokens without order sort to the bottom
  const sortedTokens = [...usedTokens].sort((a, b) => {
    const orderA = tokenDefs[a]?.order ?? 9999;
    const orderB = tokenDefs[b]?.order ?? 9999;
    return orderA - orderB;
  });

  sortedTokens.forEach(token => {
    const def = tokenDefs[token];
    if (!def) return;
    if (def.ui === false) return;

    // Determine the primary meta_field
    const metaField = def.meta_field || (def.meta_fields && def.meta_fields[0]);
    if (!metaField) return;
    if (GROUP1.has(metaField)) return;

    const label = def.label || metaField;
    const value = currentProject[metaField] || '';
    const inputId = `meta-${metaField}`;

    const row = document.createElement('div');
    row.className = 'form-group';
    row.style.marginBottom = '0.5rem';
    row.innerHTML = `
      <label class="form-label" for="${inputId}">${escHtml(label)}</label>
      <input class="form-input" type="text" id="${inputId}"
        data-meta-field="${metaField}"
        placeholder="${escHtml(label)}"
        value="${escHtml(value)}"
        style="font-size:0.82rem">`;
    container.appendChild(row);
  });

  // One delegated blur listener covers all meta fields — Group 1 fixed inputs
  // (build-title etc.) already have data-meta-field in index.html; dynamic
  // fields above also have it. No per-field hardcoding.
  document.getElementById('overview-metadata').onblur = async e => {
    const input = e.target.closest('[data-meta-field]');
    if (!input) return;
    const field = input.dataset.metaField;
    const value = input.value.trim();
    try {
      await apiFetch('PATCH', `/projects/${currentProject.id}`, { [field]: value });
      currentProject[field] = value;
      _renderOverviewInfo(); // instant update — reads from memory, no API calls
      loadOverview();        // background refresh for chapters/footnotes/build lines
    } catch(err) { console.error('meta save:', field, err); }
  };
}

// ── CSS Tokens panel ──────────────────────────────────────────────────────────

async function loadCssTokensPanel() {
  if (!currentProject) return;
  const card      = document.getElementById('overview-css-tokens');
  const container = document.getElementById('css-token-fields');
  container.innerHTML = '';

  let tokens = {};
  try {
    tokens = await apiFetch('GET', `/projects/${currentProject.id}/css-tokens`);
  } catch(e) {
    console.error('loadCssTokensPanel:', e);
    if (card) card.style.display = 'none';
    return;
  }

  if (!Object.keys(tokens).length) {
    if (card) card.style.display = 'none';
    return;
  }
  if (card) card.style.display = '';

  for (const [token, cfg] of Object.entries(tokens)) {
    const inputId = `css-token-${token.replace(/[{}]/g, '')}`;
    const row = document.createElement('div');
    row.className = 'form-group';
    row.style.marginBottom = '0.5rem';
    row.innerHTML = `
      <label class="form-label" for="${inputId}" style="font-size:0.72rem">${escHtml(cfg.label)}</label>
      <input class="form-input" type="text" id="${inputId}"
        data-css-token="${escHtml(token)}"
        placeholder="${escHtml(cfg.default)}"
        value="${escHtml(cfg.value)}"
        style="font-size:0.78rem">`;
    container.appendChild(row);

    const input = row.querySelector('input');
    input.addEventListener('blur', async () => {
      const val = input.value.trim() || cfg.default;
      try {
        await apiFetch('PUT', `/projects/${currentProject.id}/css-tokens`, { [token]: val });
        if (typeof invalidateCssTokensCache === 'function') invalidateCssTokensCache();
      } catch(e) { console.error('saveCssToken:', e); }
    });
  }
}