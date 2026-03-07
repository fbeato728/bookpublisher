'use strict';

// ── Monaco init ─────────────────────────────────────────────────────────────
function initMonaco(cb) {
  if (monacoReady) { cb(); return; }
  if (window.monacoFailed) { cb(new Error('Monaco not available')); return; }
  require.config({ paths: { vs: window.monacoBase } });
  require(['vs/editor/editor.main'], () => { monacoReady = true; cb(); });
}

// ── Navigation ───────────────────────────────────────────────────────────────
function showPanel(name) {
  if (name !== 'editor' && previewVisible) togglePreviewPane();
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  document.querySelector(`[data-panel="${name}"]`)?.classList.add('active');
  document.getElementById('fs-control').style.display =
    (name === 'split' || name === 'editor') ? 'flex' : 'none';
  if (name === 'overview' && currentProject) loadOverview();
  if (name === 'build' && currentProject) { 
    console.log('showPanel: switching to build, preserving file', buildPreviewFile);
    const preserveFile = buildPreviewFile;  // Save the currently previewed file
    buildConfig = null; 
    loadBuildConfig().then(() => {
      console.log('showPanel: loadBuildConfig complete, buildConfig loaded');
      // After config reloads, restore the preview
      if (preserveFile && buildConfig) {
        console.log('showPanel: attempting to restore preview for', preserveFile);
        console.log('showPanel: buildProfile =', buildProfile);
        const item = [...(buildConfig[buildProfile]?.front_matter || []),
                      ...(buildConfig[buildProfile]?.back_matter || [])].find(i => {
                        console.log('showPanel: checking item', i.filename, 'vs', preserveFile);
                        return i.filename === preserveFile || i.id === preserveFile;
                      });
        console.log('showPanel: found item?', !!item, item);
        if (item) {
          console.log('showPanel: calling previewBuildItem');
          previewBuildItem(item);
        } else {
          console.log('showPanel: item not found in config');
        }
      } else {
        console.log('showPanel: no file to preserve or no buildConfig');
      }
    });
    loadImageList(); 
    loadFootnotes(); 
  }
  if (name === 'split'  && currentProject) loadFullXhtml();
  if (name === 'editor' && currentProject) { loadChapterList(); loadIgnoreWords(); loadFootnotes(); }
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
      el.onclick = () => openProject(p);
      list.appendChild(el);
    });
  } catch(e) { console.error('loadProjects:', e); }
}

function openProject(p) {
  if (currentProject?.id !== p.id) {
    splitSavedData = [];
    splitProjectId = null;
    splitMarkers   = [];
    currentChapterFile = null;
    currentStylesheet = '../styles/main.css'; // Reset to default stylesheet
    isDirty = false;
    chaptersDirty   = false;
    chaptersEditing = [];
    document.getElementById('editor-filename').textContent = '— no file open —';
    document.getElementById('editor-content').innerHTML = '';
    document.getElementById('editor-content').dataset.rawXhtml = '';
    setEditorStatus('', '');
  }
  currentProject = p;
  document.getElementById('topbar-project').textContent = p.title || p.id;
  document.getElementById('project-nav').style.display = 'block';
  document.querySelectorAll('.project-item').forEach(el =>
    el.classList.toggle('active', el.title === p.id)
  );
  // Route to Editor if chapters already exist, otherwise Split
  //fetch(`${API}/projects/${p.id}/chapters`)
  //  .then(r => r.json())
  //  .then(chapters => showPanel(chapters.length ? 'editor' : 'split'))
  //  .catch(() => showPanel('split'));
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
const uploadArea = document.getElementById('upload-area');
const fileInput  = document.getElementById('file-input');

uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag'));
uploadArea.addEventListener('drop', e => {
  e.preventDefault(); uploadArea.classList.remove('drag');
  if (e.dataTransfer.files[0]) {
    const f = e.dataTransfer.files[0];
    if (f.name.endsWith('.epub') && uploadMode !== 'epub') setUploadMode('epub');
    handleFile(f);
  }
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

function handleFile(file) {
  document.getElementById('upload-text').innerHTML =
    `<strong>${file.name}</strong><br><span style="color:var(--text3)">${(file.size/1024).toFixed(0)} KB — ready to upload</span>`;
  const pid = document.getElementById('input-project-id');
  if (!pid.value) pid.value = file.name.replace(/\.[^.]+$/,'').toLowerCase().replace(/[^a-z0-9]/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'');
  const tit = document.getElementById('input-title');
  if (!tit.value) tit.value = file.name.replace(/\.[^.]+$/,'');
}

document.getElementById('btn-upload').addEventListener('click', uploadManuscript);

async function uploadManuscript() {
  const file      = fileInput.files[0];
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

    // Save default build config with front matter pre-populated, chapters from import if any
    // Key order: front_matter → chapters → back_matter (matches spine reading order)
    const chapterEntries = (data.chapters || []).map(ch => ({ filename: typeof ch === 'string' ? ch : ch.filename, enabled: true }));
    const defaultConfig = {
      digital: {
        front_matter: JSON.parse(JSON.stringify(BUILD_DEFAULTS.digital.front_matter)),
        chapters: chapterEntries,
        back_matter:  JSON.parse(JSON.stringify(BUILD_DEFAULTS.digital.back_matter)),
      },
      print: {
        front_matter: JSON.parse(JSON.stringify(BUILD_DEFAULTS.print.front_matter)),
        chapters: chapterEntries,
        back_matter:  JSON.parse(JSON.stringify(BUILD_DEFAULTS.print.back_matter)),
      },
    };
    await apiFetch('POST', `/projects/${data.id}/build-config`, defaultConfig);

    await loadProjects();
    openProject(data);
    // Reset upload form
    fileInput.value = '';
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
  const info = document.getElementById('overview-info');
  const status = document.getElementById('overview-status');
  info.innerHTML = 'Loading…';
  try {
    let chapters = [], hasBuild = false;
    try { chapters = await apiFetch('GET', `/projects/${currentProject.id}/chapters`); } catch {}
    try { await apiFetch('GET', `/projects/${currentProject.id}/build-config`); hasBuild = true; } catch {}

    info.innerHTML = `
      <div><span style="color:var(--text3)">Project ID</span>&emsp;${currentProject.id}</div>
      <div><span style="color:var(--text3)">Title</span>&emsp;${currentProject.title || '—'}</div>
      <div><span style="color:var(--text3)">Author</span>&emsp;${currentProject.author || '—'}</div>
      <div><span style="color:var(--text3)">full.xhtml</span>&emsp;✓</div>
      <div><span style="color:var(--text3)">Chapters</span>&emsp;${chapters.length ? chapters.length + ' files' : '— none'}</div>
      <div><span style="color:var(--text3)">Build config</span>&emsp;${hasBuild ? '✓' : '—'}</div>
    `;
    status.innerHTML = '';
  } catch(e) {
    info.innerHTML = `<span style="color:var(--accent)">${e.message}</span>`;
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
    document.getElementById('project-nav').style.display = 'none';
    await loadProjects();
    showPanel('welcome');
  } catch(e) { showStatus('overview-status', '✗ ' + e.message, 'err'); }
}

async function resetProject() {
  if (!currentProject) return;
  if (!confirm(`Reset project "${currentProject.id}"?\n\nThis will delete all chapters, images, build config and footnotes, keeping only the original document and full.xhtml.`)) return;
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/reset`);
    buildConfig = null;
    showStatus('overview-status', '✓ Project reset', 'ok');
    loadOverview();
  } catch(e) { showStatus('overview-status', '✗ ' + e.message, 'err'); }
}

