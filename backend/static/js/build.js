'use strict';

// ── Build panel ───────────────────────────────────────────────────────────────
let buildConfig   = null;
let buildProfile  = 'digital';

const BUILD_DEFAULTS = {
  digital: {
    front_matter: [
      { filename: 'cover_digital.xhtml', type: 'titlepage' },
      { filename: 'credits_digital.xhtml', type: 'credits' },
    ],
    back_matter: [],
  },
  print: {
    front_matter: [
      { filename: 'title_only.xhtml', type: 'title_only' },
      { filename: 'credits_print.xhtml', type: 'credits' },
      { filename: 'inside_cover_print.xhtml', type: 'titlepage' },
      { filename: 'taula.xhtml', type: 'taula' },
    ],
    back_matter: [],
  },
};

function setBuildProfile(profile) {
  buildProfile = profile;
  document.getElementById('build-tab-digital').classList.toggle('active', profile === 'digital');
  document.getElementById('build-tab-print').classList.toggle('active',   profile === 'print');
  document.getElementById('build-profile-badge').textContent = profile;
  document.getElementById('btn-hyphenate').disabled = true;
  document.getElementById('btn-dehyphenate').disabled = true;
  renderBuildPanel();
}

async function loadBuildConfig() {
  if (!currentProject) return;
  try {
    buildConfig = await apiFetch('GET', `/projects/${currentProject.id}/build-config`);
    normalizeBuildConfig(buildConfig);
  } catch(e) { buildConfig = null; }
  renderBuildPanel();
}

function normalizeBuildConfig(config) {
  // Convert old format (id/label) to new format (filename)
  ['digital', 'print'].forEach(profile => {
    if (!config[profile]) return;
    ['front_matter', 'back_matter'].forEach(section => {
      (config[profile][section] || []).forEach(item => {
        // If it has id but no filename, convert it
        if (item.id && !item.filename) {
          item.filename = item.id.endsWith('.xhtml') ? item.id : (item.id + '.xhtml');
        }
      });
    });
  });
}

function renderBuildPanel() {
  if (!buildConfig) {
    document.getElementById('build-front-list').innerHTML =
      '<div style="font-family:var(--mono);font-size:0.72rem;color:var(--text3);padding:0.5rem 0">Select a project first.</div>';
    document.getElementById('build-chapter-list').innerHTML = '';
    document.getElementById('build-back-list').innerHTML = '';
    document.getElementById('btn-hyphenate').disabled = true;
    document.getElementById('btn-dehyphenate').disabled = true;
    return;
  }
  document.getElementById('btn-hyphenate').disabled = false;
  document.getElementById('btn-dehyphenate').disabled = false;
  const prof = buildConfig[buildProfile];
  if (currentProject) {
    document.getElementById('build-author').value   = currentProject.author    || '';
    document.getElementById('build-language').value  = currentProject.language  || 'ca';
    document.getElementById('build-publisher').value = currentProject.publisher || 'BonPort';
  }
  renderBuildList('build-front-list',   prof.front_matter || [], 'front');
  renderBuildList('build-back-list',    prof.back_matter  || [], 'back');
  renderChapterList('build-chapter-list', prof.chapters   || []);
}

let buildPreviewFile = null;

function renderBuildList(containerId, items, section) {
  const el = document.getElementById(containerId);
  if (!items.length) {
    el.innerHTML = '<div style="font-family:var(--mono);font-size:0.72rem;color:var(--text3);padding:0.35rem 0">— empty —</div>';
    return;
  }
  el.innerHTML = '';
  items.forEach((item, idx) => {
    const div = document.createElement('div');
    div.className = 'build-item';
    div.dataset.idx = idx;
    div.dataset.section = section;
    div.style.cursor = 'pointer';
    div.draggable = true;
    div.innerHTML = `
      <span class="bi-handle" title="Drag to reorder" style="cursor:grab">⠿</span>
      <span class="bi-type">${escHtml(item.type || 'file')}</span>
      <span class="bi-label" title="${escHtml(item.filename || item.id || '')}">${escHtml(item.filename || item.id || '')}</span>
      <button class="bi-toggle" title="Edit filename" onclick="event.stopPropagation();startBuildItemRename(this, '${section}', ${idx})">✎</button>
      <button class="bi-toggle" title="Delete" onclick="event.stopPropagation();deleteBuildItem('${section}', ${idx})">×</button>
    `;
    div.addEventListener('click', () => previewBuildItem(item));

    // ── Drag-to-reorder ──────────────────────────────────────────────────
    div.addEventListener('dragstart', e => {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', idx);
      setTimeout(() => div.style.opacity = '0.4', 0);
    });
    div.addEventListener('dragend', () => {
      div.style.opacity = '';
      el.querySelectorAll('.build-item').forEach(d => d.style.borderTop = '');
    });
    div.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      el.querySelectorAll('.build-item').forEach(d => d.style.borderTop = '');
      div.style.borderTop = '2px solid var(--accent)';
    });
    div.addEventListener('dragleave', () => {
      div.style.borderTop = '';
    });
    div.addEventListener('drop', e => {
      e.preventDefault(); e.stopPropagation();
      div.style.borderTop = '';
      const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
      const toIdx   = idx;
      if (fromIdx === toIdx) return;
      const key  = section === 'front' ? 'front_matter' : 'back_matter';
      const arr  = buildConfig[buildProfile][key];
      const [moved] = arr.splice(fromIdx, 1);
      arr.splice(toIdx, 0, moved);
      saveBuildConfig();
      renderBuildPanel();
    });

    el.appendChild(div);
  });
}

// ── Chapter list state ────────────────────────────────────────────────────────
let chaptersDirty    = false;
let chaptersEditing  = [];   // working copy while editing

function markChaptersDirty() {
  chaptersDirty = true;
  document.getElementById('chapters-dirty-badge').style.display = '';
  document.getElementById('btn-save-chapters').style.display = '';
}

function clearChaptersDirty() {
  chaptersDirty = false;
  document.getElementById('chapters-dirty-badge').style.display = 'none';
  document.getElementById('btn-save-chapters').style.display = 'none';
}

function renderChapterList(containerId, chapters) {
  // Keep a working copy for edits; only reset if not dirty
  if (!chaptersDirty) {
    chaptersEditing = chapters.map(ch => ({ ...ch }));
  }
  _renderChaptersFromEditing(containerId);
}

function _renderChaptersFromEditing(containerId) {
  const el = document.getElementById(containerId);
  el.innerHTML = '';
  if (!chaptersEditing.length) {
    el.innerHTML = '<div style="font-family:var(--mono);font-size:0.72rem;color:var(--text3);padding:0.35rem 0">— no chapters —</div>';
    return;
  }
  chaptersEditing.forEach((ch, idx) => {
    const div = document.createElement('div');
    div.className = 'build-item';
    div.dataset.idx = idx;
    div.draggable = true;
    div.innerHTML = `
      <span class="bi-handle" title="Drag to reorder">⠿</span>
      <span class="bi-type">${escHtml(ch.type || 'chapter')}</span>
      <span class="bi-label" title="${escHtml(ch.filename)}">${escHtml(ch.filename)}</span>
      <button class="bi-toggle" title="Edit filename" onclick="event.stopPropagation();startChapterRename(this, ${idx})">✎</button>
      <button class="bi-toggle" title="Delete" onclick="event.stopPropagation();deleteChapterEntry(${idx})">×</button>
    `;

    // Click to preview
    div.addEventListener('click', () => previewBuildItem(ch));

    // Drag to reorder
    div.addEventListener('dragstart', e => {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', idx);
      setTimeout(() => div.style.opacity = '0.4', 0);
    });
    div.addEventListener('dragend', () => {
      div.style.opacity = '';
      el.querySelectorAll('.build-item').forEach(d => d.style.borderTop = '');
    });
    div.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      el.querySelectorAll('.build-item').forEach(d => d.style.borderTop = '');
      div.style.borderTop = '2px solid var(--accent)';
    });
    div.addEventListener('dragleave', () => div.style.borderTop = '');
    div.addEventListener('drop', e => {
      e.preventDefault(); e.stopPropagation();
      div.style.borderTop = '';
      const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
      if (fromIdx === idx) return;
      const [moved] = chaptersEditing.splice(fromIdx, 1);
      chaptersEditing.splice(idx, 0, moved);
      markChaptersDirty();
      _renderChaptersFromEditing(containerId);
    });

    el.appendChild(div);
  });
}

function startChapterRename(btn, idx) {
  const ch    = chaptersEditing[idx];
  const item  = btn.closest('.build-item');
  const label = item.querySelector('.bi-label');

  label.style.display = 'none';
  btn.style.display   = 'none';
  const input = document.createElement('input');
  input.type  = 'text';
  input.value = ch.filename;
  input.style.cssText = 'flex:1;font-size:0.82rem;padding:0.1rem 0.4rem;background:var(--surface2);border:1px solid var(--accent);border-radius:3px;color:var(--text);font-family:var(--mono)';
  item.insertBefore(input, btn);
  input.focus(); input.select();

  function commit() {
    const newFilename = input.value.trim();
    if (newFilename && newFilename !== ch.filename) {
      chaptersEditing[idx].filename = newFilename;
      markChaptersDirty();
    }
    input.remove();
    label.textContent = chaptersEditing[idx].filename;
    label.style.display = '';
    btn.style.display   = '';
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.remove(); label.style.display = ''; btn.style.display = ''; }
  });
}

function deleteChapterEntry(idx) {
  if (!confirm(`Delete "${chaptersEditing[idx].name || chaptersEditing[idx].filename}"?\nThis will remove the file from disk.`)) return;
  chaptersEditing.splice(idx, 1);
  markChaptersDirty();
  _renderChaptersFromEditing('build-chapter-list');
}

async function saveChapters() {
  if (!currentProject || !buildConfig) return;
  const btn = document.getElementById('btn-save-chapters');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';

  // Build the desired state: original filename → new name mapping, ordered list
  const desired = chaptersEditing.map(ch => ({ filename: ch.filename, name: ch.name, type: ch.type || 'chapter' }));

  // Compute deletes: filenames in current buildConfig not in desired
  const desiredSet   = new Set(desired.map(c => c.filename));
  const currentChaps = buildConfig[buildProfile]?.chapters || [];
  const toDelete     = currentChaps.filter(c => !desiredSet.has(c.filename)).map(c => c.filename);

  try {
    await apiFetch('POST', `/projects/${currentProject.id}/chapters/sync`, { chapters: desired, delete: toDelete });

    // Update both profiles in buildConfig
    ['digital', 'print'].forEach(p => { buildConfig[p].chapters = desired.map(ch => ({ ...ch, enabled: true })); });
    await saveBuildConfig();
    clearChaptersDirty();
    renderBuildPanel();
    showStatus('build-status', '✓ Chapters saved', 'ok');
  } catch(e) { showStatus('build-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = 'Save'; }
}

async function addBuildChapter() {
  if (!currentProject || !buildConfig) return;
  const name = prompt('Chapter name:');
  if (!name || !name.trim()) return;
  const typeVal = prompt('Type (chapter / part / record):', 'chapter') || 'chapter';

  const slug       = name.trim().toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  const filename   = `${typeVal}_${slug}.xhtml`;

  // Create the file on disk now so it exists when Save is clicked
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/chapters`, { filename, name: name.trim(), type: typeVal });
  } catch(e) { showStatus('build-status', '✗ ' + e.message, 'err'); return; }

  chaptersEditing.push({ filename, name: name.trim(), type: typeVal, enabled: true });
  markChaptersDirty();
  _renderChaptersFromEditing('build-chapter-list');
  showStatus('build-status', `✓ ${filename} added — click Save to confirm`, 'ok');
}

async function addNewCss() {
  if (!currentProject) return;
  const name = prompt('CSS filename (without .css extension):');
  if (!name || !name.trim()) return;
  const filename = name.trim().toLowerCase().replace(/[^a-z0-9-_]/g, '-') + '.css';
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/styles`, { filename });
    showStatus('build-action-status', `✓ ${filename} created — open in Editor`, 'ok');
  } catch(e) { showStatus('build-action-status', '✗ ' + e.message, 'err'); }
}

function startBuildItemRename(btn, section, idx) {
  const key  = section === 'front' ? 'front_matter' : 'back_matter';
  const item = buildConfig[buildProfile][key][idx];
  const div  = btn.closest('.build-item');
  const label = div.querySelector('.bi-label');

  // Get current filename from either filename or id field
  const currentFilename = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : '');

  label.style.display = 'none';
  btn.style.display   = 'none';
  const input = document.createElement('input');
  input.type  = 'text';
  input.value = currentFilename;
  input.style.cssText = 'flex:1;font-size:0.82rem;padding:0.1rem 0.4rem;background:var(--surface2);border:1px solid var(--accent);border-radius:3px;color:var(--text);font-family:var(--mono)';
  div.insertBefore(input, btn);
  input.focus(); input.select();

  function commit() {
    let newFilename = input.value.trim();
    if (!newFilename) return;
    
    // Auto-add .xhtml if no extension
    if (!newFilename.includes('.')) {
      newFilename = newFilename + '.xhtml';
    } else if (!newFilename.endsWith('.xhtml')) {
      showStatus('build-status', '✗ Only .xhtml files are supported', 'err');
      input.remove();
      label.style.display = '';
      btn.style.display   = '';
      return;
    }
    
    if (newFilename !== currentFilename) {
      item.filename = newFilename;
      if (item.id) delete item.id; // Remove old format field
      saveBuildConfig();
    }
    input.remove();
    label.textContent = newFilename;
    label.style.display = '';
    btn.style.display   = '';
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { input.remove(); label.style.display = ''; btn.style.display = ''; }
  });
}

function deleteBuildItem(section, idx) {
  const key = section === 'front' ? 'front_matter' : 'back_matter';
  const item = buildConfig[buildProfile][key][idx];
  if (!confirm(`Delete "${item.filename}"?\nThis will remove the file from disk.`)) return;
  buildConfig[buildProfile][key].splice(idx, 1);
  saveBuildConfig(); renderBuildPanel();
}

async function addBuildItem(section) {
  const input = prompt('Filename\ne.g. cover, credits, epilogue\n(will add .xhtml automatically):');
  if (!input || !input.trim()) return;
  
  let cleanFilename = input.trim().toLowerCase();
  
  // Check if has extension
  if (cleanFilename.includes('.')) {
    // Has extension - must be .xhtml
    if (!cleanFilename.endsWith('.xhtml')) {
      showStatus('build-status', '✗ Only .xhtml files are supported', 'err');
      return;
    }
  } else {
    // No extension - add .xhtml
    cleanFilename = cleanFilename + '.xhtml';
  }
  
  console.log('addBuildItem: creating file', cleanFilename, 'in section', section);
  
  const key      = section === 'front' ? 'front_matter' : 'back_matter';
  try {
    console.log('addBuildItem: checking if file exists at', `/projects/${currentProject.id}/xhtml/${cleanFilename}`);
    try {
      await apiFetch('GET', `/projects/${currentProject.id}/xhtml/${cleanFilename}`);
      console.log('addBuildItem: file already exists');
    } catch {
      console.log('addBuildItem: file does not exist, attempting to create...');
      try {
        const createData = await apiFetch('POST', `/projects/${currentProject.id}/xhtml/${cleanFilename}`);
        console.log('addBuildItem: file created successfully, response:', createData);
      } catch(createErr) {
        console.error('addBuildItem: POST response error', createErr);
        if (!createErr.message.includes('File already exists')) {
          showStatus('build-status', '✗ Could not create file: ' + createErr.message, 'err');
          return;
        }
      }
    }
  } catch(e) {
    console.error('addBuildItem: fetch error', e);
    showStatus('build-status', '✗ ' + e.message, 'err'); return;
  }
  
  console.log('addBuildItem: adding to buildConfig');
  buildConfig[buildProfile][key].push({ filename: cleanFilename, type: 'custom' });
  await saveBuildConfig();
  renderBuildPanel();
  const item = buildConfig[buildProfile][key].slice(-1)[0];
  console.log('addBuildItem: calling previewBuildItem with item', item);
  await previewBuildItem(item);
}

async function previewBuildItem(item) {
  // Handle both new format (filename) and old format (id)
  const filename = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : null);
  if (!filename) {
    console.error('previewBuildItem: no filename in item', item);
    document.getElementById('build-preview-body').innerHTML = '<p style="font-family:var(--mono);font-size:0.72rem;color:var(--accent)">Error: Invalid item</p>';
    return;
  }
  
  console.log('previewBuildItem: setting buildPreviewFile to', filename);
  buildPreviewFile = filename;
  document.getElementById('build-preview-filename').textContent = filename;
  document.getElementById('btn-build-preview-edit').style.display = '';
  const body = document.getElementById('build-preview-body');
  const bodyParent = body?.parentElement;
  const bodyGrandparent = bodyParent?.parentElement;
  console.log('previewBuildItem: body element found?', !!body, 'display:', body?.style.display);
  console.log('previewBuildItem: body parent display:', bodyParent?.style.display, 'class:', bodyParent?.className);
  console.log('previewBuildItem: body grandparent display:', bodyGrandparent?.style.display, 'class:', bodyGrandparent?.className);
  console.log('previewBuildItem: computed body display:', window.getComputedStyle(body)?.display);
  body.innerHTML = '<span style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">Loading…</span>';

  try {
    let data;
    try {
      data = await apiFetch('GET', `/projects/${currentProject.id}/xhtml/${filename}?t=${Date.now()}`);
    } catch {
      console.warn('previewBuildItem: file not found or error');
      body.innerHTML = `<p style="font-family:var(--mono);font-size:0.72rem;color:var(--accent)">⚠ File not found: ${escHtml(filename)}</p>`;
      document.getElementById('btn-build-preview-edit').style.display = '';
      return;
    }
    const parser = new DOMParser();
    const doc    = parser.parseFromString(data.content, 'application/xhtml+xml');
    const bel    = doc.querySelector('body');
    
    if (bel) {
      // Extract first 3 elements with text content
      const children = Array.from(bel.children);
      const preview = [];
      for (const el of children) {
        if (preview.length >= 3) break;
        const text = el.textContent?.trim();
        if (text) {
          preview.push(`<${el.tagName.toLowerCase()}>${escHtml(text.substring(0, 100))}${text.length > 100 ? '…' : ''}</${el.tagName.toLowerCase()}>`);
        }
      }
      const html = preview.length ? preview.join('<br/>') : '<p style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">(empty file)</p>';
      console.log('previewBuildItem: setting innerHTML, length =', html.length);
      body.innerHTML = html;
      body.style.backgroundColor = '#F8F8FF';  // Yellow background for debugging
      body.style.color = '#000000';  // Black text for debugging
      console.log('previewBuildItem: innerHTML set, body.innerHTML.length =', body.innerHTML.length);
    } else {
      body.innerHTML = data.content;
    }
    
    const src      = data.source === 'global' ? '⚠ global template' : '✓ project file';
    const srcColor = data.source === 'global' ? 'var(--amber)' : 'var(--green)';
    document.getElementById('build-preview-filename').innerHTML =
      `${escHtml(filename)} <span style="color:${srcColor};font-size:0.6rem">${src}</span>`;
    console.log('previewBuildItem: preview loaded successfully');
  } catch(e) {
    console.error('previewBuildItem: error', e);
    body.innerHTML = `<p style="font-family:var(--mono);font-size:0.72rem;color:var(--accent)">Error: ${escHtml(e.message)}</p>`;
  }
}

async function showBuildFilePicker(item, body) {
  let files = [];
  try { files = await apiFetch('GET', `/projects/${currentProject.id}/xhtml`); } catch(e) {}
  
  // Handle both new format (filename) and old format (id)
  const filename = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : null);
  const wanted  = filename || 'unknown';
  const baseName = (filename || '').replace(/\.xhtml$/, '');
  const matches = files.filter(f => baseName && (f.includes(baseName) || f === filename));
  const others  = files.filter(f => !matches.includes(f));
  let html = `<div style="font-family:var(--mono);font-size:0.72rem;color:var(--accent);margin-bottom:0.75rem">
    ✗ <strong>${escHtml(wanted)}</strong> not found
  </div>
  <div style="font-family:var(--mono);font-size:0.65rem;color:var(--text3);margin-bottom:0.5rem;text-transform:uppercase;letter-spacing:0.08em">
    Files in xhtml/ — click to assign &amp; preview
  </div>`;
  if (matches.length) {
    html += `<div style="font-family:var(--mono);font-size:0.65rem;color:var(--amber);margin-bottom:0.3rem">Likely matches:</div>`;
    matches.forEach(f => { html += `<div class="build-file-pick" onclick="assignBuildFile('${escHtml(filename)}', '${escHtml(f)}')">${escHtml(f)}</div>`; });
    html += `<div style="margin-top:0.5rem"></div>`;
  }
  if (others.length) {
    html += `<div style="font-family:var(--mono);font-size:0.65rem;color:var(--text3);margin-bottom:0.3rem">All files:</div>`;
    others.forEach(f => { html += `<div class="build-file-pick" onclick="assignBuildFile('${escHtml(filename)}', '${escHtml(f)}')">${escHtml(f)}</div>`; });
  }
  if (!files.length) html += `<p style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">No xhtml files found in this project.</p>`;
  body.innerHTML = html;
}

async function assignBuildFile(oldFilename, newFilename) {
  // Ensure filenames have .xhtml extension
  const normalizedOld = oldFilename && !oldFilename.endsWith('.xhtml') ? oldFilename + '.xhtml' : oldFilename;
  const normalizedNew = newFilename && !newFilename.endsWith('.xhtml') ? newFilename + '.xhtml' : newFilename;
  
  ['front_matter', 'back_matter'].forEach(key => {
    (buildConfig[buildProfile][key] || []).forEach(item => {
      // Handle both filename and id fields
      const itemFilename = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : null);
      if (itemFilename === normalizedOld) { 
        item.filename = normalizedNew;
        // Also update id for backward compatibility if needed
        if (item.id) delete item.id;
      }
    });
  });
  await saveBuildConfig(); renderBuildPanel();
  const item = [...(buildConfig[buildProfile].front_matter || []),
                ...(buildConfig[buildProfile].back_matter  || [])].find(i => (i.filename || i.id) === normalizedNew || (i.filename === normalizedNew));
  if (item) previewBuildItem(item);
}

async function openBuildItemInEditor() {
  console.log('openBuildItemInEditor called! buildPreviewFile =', buildPreviewFile);
  
  if (!buildPreviewFile) {
    console.error('openBuildItemInEditor: buildPreviewFile is not set');
    showStatus('build-status', '✗ No file selected in preview', 'err');
    return;
  }
  
  console.log('openBuildItemInEditor: opening', buildPreviewFile);
  
  // Show editor panel
  showPanel('editor');
  
  // Open the file directly (same logic as openChapter)
  if (isDirty && currentChapterFile) {
    if (!confirm('You have unsaved changes. Discard them?')) return;
  }
  
  document.querySelectorAll('.editor-fileitem').forEach(e => e.classList.remove('active'));
  currentChapterFile = buildPreviewFile;
  document.getElementById('editor-filename').textContent = buildPreviewFile;
  setEditorStatus('Loading…', '');
  ltMatches = []; isDirty = false; fileIsHyphenated = false;

  const isCss = buildPreviewFile.endsWith('.css');
  const openPath = isCss ? `/projects/${currentProject.id}/styles/${buildPreviewFile}`
                         : `/projects/${currentProject.id}/xhtml/${buildPreviewFile}`;

  console.log('openBuildItemInEditor: fetching from', openPath);

  try {
    const data = await apiFetch('GET', `${openPath}?t=${Date.now()}`);

    if (isCss) {
      // CSS opens in code mode
      if (editorMode !== 'code') await switchToCodeMode();
      if (monacoEditor) {
        const model = monacoEditor.getModel();
        if (model) monaco.editor.setModelLanguage(model, 'css');
        monacoLoading = true;
        monacoEditor.setValue(data.content);
        monacoLoading = false;
        setTimeout(() => { isDirty = false; }, 0);
      }
      document.querySelectorAll('.lt-only').forEach(el => el.style.display = 'none');
      document.getElementById('btn-toggle-mode').style.display = 'none';
      document.getElementById('btn-preview-file').style.display = 'none';
      if (previewVisible) togglePreviewPane();
      setEditorStatus(data.source === 'global' ? '⚠ Loaded from global — save to create project override' : '', data.source === 'global' ? 'warn' : '');
    } else {
      // XHTML file - switch to text mode first to show the editor-content div
      console.log('openBuildItemInEditor: XHTML file detected, current editorMode =', editorMode);
      
      // Force text mode
      if (editorMode !== 'text') {
        console.log('openBuildItemInEditor: switching to text mode');
        switchToTextMode();
      }
      
      // Ensure editor-scroll is visible
      document.getElementById('editor-scroll').classList.add('active');
      document.getElementById('monaco-container').classList.remove('active');
      editorMode = 'text';
      console.log('openBuildItemInEditor: forced text mode visibility');
      
      document.getElementById('btn-toggle-mode').style.display = '';
      document.getElementById('btn-preview-file').style.display = '';
      const parser = new DOMParser();
      const doc    = parser.parseFromString(data.content, 'application/xhtml+xml');
      
      // Extract stylesheet href
      const linkEl = doc.querySelector('link[rel="stylesheet"]');
      if (linkEl) {
        currentStylesheet = linkEl.getAttribute('href') || '../styles/main.css';
      } else {
        currentStylesheet = '../styles/main.css';
      }
      
      // Load content into editor with footnote conversion
      const bel = doc.querySelector('body');
      if (!bel) { setEditorStatus('Invalid XHTML: no body element', 'err'); return; }
      
      // Convert footnote comments to markers for display
      let bodyHtml = bel.innerHTML;
      bodyHtml = bodyHtml.replace(/<!--fn:(\d+)(?::(\w+))?-->/g, (_, n, v) => {
        const variant = v || 'def';
        const label   = variant === 'def' ? `[fn:${n}]` : `[fn:${n}:${variant}]`;
        return `<span class="fn-marker" data-fn="${n}" data-variant="${variant}" contenteditable="false">${label}</span>`;
      });
      
      console.log('openBuildItemInEditor: setting editor-content, length =', bodyHtml.length);
      const editorContentEl = document.getElementById('editor-content');
      editorContentEl.innerHTML = bodyHtml;
      editorContentEl.dataset.rawXhtml = data.content;
      console.log('openBuildItemInEditor: content set successfully');
      
      // Check for grammar (only if project file)
      if (data.source === 'project') {
        // Only do grammar check in text mode
        if (editorMode === 'text') {
          document.querySelectorAll('.lt-only').forEach(el => el.style.display = '');
          await checkGrammar();
        } else {
          document.querySelectorAll('.lt-only').forEach(el => el.style.display = 'none');
        }
      } else {
        document.querySelectorAll('.lt-only').forEach(el => el.style.display = 'none');
        setEditorStatus('⚠ Loaded from global — save to create project override', 'warn');
      }
    }
    console.log('openBuildItemInEditor: file loaded successfully');
  } catch(e) {
    console.error('openBuildItemInEditor: error', e);
    setEditorStatus(`✗ ${e.message}`, 'err');
    document.getElementById('editor-content').innerHTML = '';
  }
}

