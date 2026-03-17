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
  if (name === 'overview' && currentProject) loadOverview();
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
  if (name === 'editor' && currentProject) { loadChapterList(); loadIgnoreWords(); loadFootnotes(); }
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
    splitSavedData = [];
    splitProjectId = null;
    splitMarkers   = [];
    currentChapterFile = null;
    currentStylesheet = '../styles/main.css';
    isDirty = false;
    chaptersDirty   = false;
    chaptersEditing = [];
    document.getElementById('editor-filename').textContent = '— no file open —';
    document.getElementById('editor-content').innerHTML = '';
    document.getElementById('editor-content').dataset.rawXhtml = '';
    setEditorStatus('', '');
    showSplitsView();
  }
  currentProject = p;
  document.getElementById('topbar-project').textContent = p.id;
  document.getElementById('project-nav').classList.remove('hidden');
  document.querySelectorAll('.project-item').forEach(el =>
    el.classList.toggle('active', el.dataset.projectId === p.id)
  );
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
      <div><span style="color:var(--text3)">full.xhtml</span>&emsp;✓</div>
      <div><span style="color:var(--text3)">Footnotes</span>&emsp;${hasFootnotes ? '✓' : '✗'}</div>
      <div><span style="color:var(--text3)">Chapters</span>&emsp;${chapters.length ? chapters.length + ' files' : '— none'}</div>
      <div><span style="color:var(--text3)">Build config</span>&emsp;${hasBuild ? '✓' : '—'}</div>
    `;

    btn.disabled    = footnotesInjected;
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
      injectBtn.style.display = footnotesInjected ? 'none' : 'inline-block';
      injectBtn.disabled      = false;
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
    buildConfig = null;
    showStatus('overview-status', '✓ Project reset', 'ok');
    loadOverview();
  } catch(e) { showStatus('overview-status', '✗ ' + e.message, 'err'); }
}