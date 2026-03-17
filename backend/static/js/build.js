'use strict';

// ── Build panel ───────────────────────────────────────────────────────────────
let buildProfile  = 'digital';
const PREVIEW_MAX_ELEMENTS = 10;
const PREVIEW_MAX_CHARS = 1800;

function setBuildProfile(profile) {
  buildProfile = profile;
  document.getElementById('build-tab-digital').classList.toggle('active', profile === 'digital');
  document.getElementById('build-tab-print').classList.toggle('active',   profile === 'print');
  document.getElementById('build-profile-badge').textContent = profile;
  document.getElementById('build-profile-label').textContent = profile === 'digital' ? 'Digital' : 'Print';
  document.getElementById('btn-hyphenate').disabled = true;
  document.getElementById('btn-dehyphenate').disabled = true;
  renderBuildPanel();
}

async function loadBuildConfig() {
  if (!currentProject) return;
  try {
    buildConfig = await apiFetch('GET', `/projects/${currentProject.id}/build-config`);
    console.log('loadBuildConfig SUCCESS:', buildConfig);
    normalizeBuildConfig(buildConfig);
  } catch(e) { 
    console.log('loadBuildConfig FAILED:', e);
    buildConfig = null; 
  }
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
  document.getElementById('build-profile-label').textContent = buildProfile === 'digital' ? 'Digital' : 'Print';
  // Show/hide print-only buttons
  const isPrint = buildProfile === 'print';
  document.querySelectorAll('.print-only-btn').forEach(btn => {
    btn.style.display = isPrint ? '' : 'none';
  });
  const prof = buildConfig[buildProfile];
  if (currentProject) {
    document.getElementById('build-author').value   = currentProject.author    || '';
    document.getElementById('build-language').value  = currentProject.language  || 'ca';
    document.getElementById('build-publisher').value = currentProject.publisher || 'BonPort';
  }
  renderBuildList('build-front-list',   prof.front_matter || [], 'front');
  renderBuildList('build-back-list',    prof.back_matter  || [], 'back');
  renderChapterList('build-chapter-list', prof.chapters   || []);
  // Blank page counters — print only
  renderBlanksRow('build-front-blanks', 'front', isPrint);
  renderBlanksRow('build-back-blanks',  'back',  isPrint);
}

let buildPreviewFile = null;

function renderBlanksRow(containerId, section, isPrint) {
  const el = document.getElementById(containerId);
  if (!isPrint) { el.classList.add('hidden'); el.innerHTML = ''; return; }
  el.classList.remove('hidden');
  const prof     = buildConfig[buildProfile];
  const keyBef   = section === 'front' ? 'blanks_before_front' : 'blanks_before_back';
  const keyAft   = section === 'front' ? 'blanks_after_front'  : 'blanks_after_back';
  const valBef   = prof[keyBef] ?? 0;
  const valAft   = prof[keyAft] ?? 0;
  const titleBef = section === 'front' ? 'Blank pages before front matter' : 'Blank pages before back matter';
  const titleAft = section === 'front' ? 'Blank pages after front matter'  : 'Blank pages after back matter';
  el.innerHTML = `
    <span class="blanks-ctrl" title="${titleBef}">
      ▢↑
      <button class="blanks-btn" onclick="setBlanks('${section}','before',-1)">−</button>
      <span class="blanks-val" id="blanks-${section}-before">${valBef}</span>
      <button class="blanks-btn" onclick="setBlanks('${section}','before',1)">+</button>
    </span>
    <span class="blanks-ctrl" title="${titleAft}">
      ▢↓
      <button class="blanks-btn" onclick="setBlanks('${section}','after',-1)">−</button>
      <span class="blanks-val" id="blanks-${section}-after">${valAft}</span>
      <button class="blanks-btn" onclick="setBlanks('${section}','after',1)">+</button>
    </span>
  `;
}

async function setBlanks(section, pos, delta) {
  if (!buildConfig || buildProfile !== 'print') return;
  const key = section === 'front'
    ? (pos === 'before' ? 'blanks_before_front' : 'blanks_after_front')
    : (pos === 'before' ? 'blanks_before_back'  : 'blanks_after_back');
  const prof   = buildConfig['print'];
  const newVal = Math.max(0, (prof[key] ?? 0) + delta);
  prof[key] = newVal;
  // Update display immediately
  const span = document.getElementById(`blanks-${section}-${pos}`);
  if (span) span.textContent = newVal;
  await saveBuildConfig();
}

async function toggleNav(section, idx) {
  if (!buildConfig || buildProfile !== 'digital') return;
  if (section === 'chapter') {
    const ch = chaptersEditing[idx];
    ch.nav = ch.nav === false ? true : false;
    buildConfig['digital'].chapters[idx].nav = ch.nav;
  } else {
    const key  = section === 'front' ? 'front_matter' : 'back_matter';
    const item = buildConfig['digital'][key][idx];
    item.nav   = item.nav ? false : true;
  }
  await saveBuildConfig();
  renderBuildPanel();
}

async function toggleToc(section, idx) {
  if (!buildConfig || buildProfile !== 'print') return;
  const key  = section === 'front' ? 'front_matter' : 'back_matter';
  const item = buildConfig['print'][key][idx];
  item.toc   = item.toc ? false : true;
  await saveBuildConfig();
  renderBuildPanel();
}

async function togglePag(idx) {
  if (!buildConfig || buildProfile !== 'print') return;
  const ch = chaptersEditing[idx];
  ch.pag = ch.pag === false ? true : false;
  buildConfig['print'].chapters[idx].pag = ch.pag;
  await saveBuildConfig();
  renderBuildPanel();
}

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
      <span class="bi-label" title="${escHtml(item.filename || item.id || '')}">${escHtml(item.filename || item.id || '')}</span>
      ${buildProfile === 'digital' ? `<button class="bi-nav${item.nav ? ' is-nav' : ''}" title="${item.nav ? 'In nav/toc — click to remove' : 'Not in nav/toc — click to add'}" onclick="event.stopPropagation();toggleNav('${section}',${idx})">${item.nav ? 'NAV' : '🚫'}</button>` : ''}
      ${buildProfile === 'print' && section === 'front' ? `<button class="bi-nav${item.toc ? ' is-nav' : ''}" title="${item.toc ? 'TOC source — click to remove' : 'Not TOC source — click to set'}" onclick="event.stopPropagation();toggleToc('${section}',${idx})">${item.toc ? 'TOC' : '🚫'}</button>` : ''}
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
// chaptersEditing lives in globals.js

// Update build_config.json only (reorder, rename)
async function _saveChapterConfig(desired) {
  ['digital', 'print'].forEach(p => { buildConfig[p].chapters = desired; });
  await saveBuildConfig();
}

function renderChapterList(containerId, chapters) {
  chaptersEditing = chapters.map(ch => ({ ...ch }));
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
      <span class="bi-label" title="${escHtml(ch.filename)}">${escHtml(ch.filename)}</span>
      ${buildProfile === 'digital' ? `<button class="bi-nav${ch.nav === false ? '' : ' is-nav'}" title="${ch.nav === false ? 'Not in nav/toc — click to add' : 'In nav/toc — click to remove'}" onclick="event.stopPropagation();toggleNav('chapter',${idx})">${ch.nav === false ? '🚫' : 'NAV'}</button>` : ''}
      ${buildProfile === 'print' ? `<button class="bi-nav${ch.pag === false ? '' : ' is-nav'}" title="${ch.pag === false ? 'Not in TOC page list — click to add' : 'In TOC page list — click to remove'}" onclick="event.stopPropagation();togglePag(${idx})">${ch.pag === false ? '🚫' : 'PAG'}</button>` : ''}
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
      const desired = chaptersEditing.map(c => ({ filename: c.filename, name: c.name, type: c.type || 'chapter', enabled: true }));
      _saveChapterConfig(desired);
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

  const stem = ch.filename.replace(/\.xhtml$/, '');
  const input = document.createElement('input');
  input.type  = 'text';
  input.value = stem;
  input.style.cssText = 'flex:1;font-size:0.82rem;padding:0.1rem 0.4rem;background:var(--surface2);border:1px solid var(--accent);border-radius:3px;color:var(--text);font-family:var(--mono)';
  const ext = document.createElement('span');
  ext.textContent = '.xhtml';
  ext.style.cssText = 'font-size:0.82rem;color:var(--text3);font-family:var(--mono);padding:0 0.2rem;align-self:center';
  item.insertBefore(input, btn);
  item.insertBefore(ext, btn);
  input.focus(); input.select();

  async function commit() {
    const newStem = input.value.trim();
    input.remove();
    ext.remove();
    label.style.display = '';
    btn.style.display   = '';
    if (!newStem || newStem === stem) {
      label.textContent = ch.filename;
      return;
    }
    const newFilename = newStem + '.xhtml';
    try {
      await apiFetch('PUT', `/projects/${currentProject.id}/xhtml/${ch.filename}/rename`, { new_filename: newFilename });
      chaptersEditing[idx].filename = newFilename;
      await _saveChapterConfig(chaptersEditing.map(c => ({ filename: c.filename, name: c.name, type: c.type || 'chapter', enabled: true })));
      _renderChaptersFromEditing('build-chapter-list');
    } catch(e) {
      showStatus('build-status', '\u2717 ' + e.message, 'err');
      label.textContent = ch.filename;
    }
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.remove(); ext.remove(); label.style.display = ''; btn.style.display = ''; }
  });
}

async function deleteChapterEntry(idx) {
  const ch = chaptersEditing[idx];
  if (!confirm(`Delete "${ch.name || ch.filename}"?\nThis will remove the file from disk.`)) return;
  try {
    await apiFetch('DELETE', `/projects/${currentProject.id}/chapters/${ch.filename}`);
  } catch(e) { showStatus('build-status', '✗ ' + e.message, 'err'); return; }
  chaptersEditing.splice(idx, 1);
  const desired = chaptersEditing.map(c => ({ filename: c.filename, name: c.name, type: c.type || 'chapter', enabled: true }));
  await _saveChapterConfig(desired);
  _renderChaptersFromEditing('build-chapter-list');
  showStatus('build-status', `✓ ${ch.filename} deleted`, 'ok');
}

async function addBuildChapter() {
  if (!currentProject || !buildConfig) return;
  const name = prompt('Chapter name:');
  if (!name || !name.trim()) return;
  const typeVal = prompt('Type (chapter / part / record):', 'chapter') || 'chapter';

  let result;
  try {
    result = await apiFetch('POST', `/projects/${currentProject.id}/chapters`, { name: name.trim(), type: typeVal });
  } catch(e) { showStatus('build-status', '✗ ' + e.message, 'err'); return; }

  const { filename } = result.chapter;
  chaptersEditing.push({ filename, name: name.trim(), type: typeVal, enabled: true });
  const desired = chaptersEditing.map(c => ({ filename: c.filename, name: c.name, type: c.type || 'chapter', enabled: true }));
  await _saveChapterConfig(desired);
  _renderChaptersFromEditing('build-chapter-list');
  showStatus('build-status', `✓ ${filename} added`, 'ok');
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

  const currentFilename = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : '');
  const stem = currentFilename.replace(/\.xhtml$/, '');

  label.style.display = 'none';
  btn.style.display   = 'none';
  const input = document.createElement('input');
  input.type  = 'text';
  input.value = stem;
  input.style.cssText = 'flex:1;font-size:0.82rem;padding:0.1rem 0.4rem;background:var(--surface2);border:1px solid var(--accent);border-radius:3px;color:var(--text);font-family:var(--mono)';
  const ext = document.createElement('span');
  ext.textContent = '.xhtml';
  ext.style.cssText = 'font-size:0.82rem;color:var(--text3);font-family:var(--mono);padding:0 0.2rem;align-self:center';
  div.insertBefore(input, btn);
  div.insertBefore(ext, btn);
  input.focus(); input.select();

  async function commit() {
    const newStem = input.value.trim();
    input.remove();
    ext.remove();
    label.style.display = '';
    btn.style.display   = '';
    if (!newStem || newStem === stem) {
      label.textContent = currentFilename;
      return;
    }
    const newFilename = newStem + '.xhtml';
    try {
      await apiFetch('PUT', `/projects/${currentProject.id}/xhtml/${currentFilename}/rename`, { new_filename: newFilename });
      item.filename = newFilename;
      if (item.id) delete item.id;
      ['digital', 'print'].forEach(p => {
        ['front_matter', 'back_matter'].forEach(sec => {
          (buildConfig[p]?.[sec] || []).forEach(i => { if (i.filename === currentFilename) i.filename = newFilename; });
        });
      });
      await saveBuildConfig();
      label.textContent = newFilename;
    } catch(e) {
      showStatus('build-status', '\u2717 ' + e.message, 'err');
      label.textContent = currentFilename;
    }
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { input.remove(); ext.remove(); label.style.display = ''; btn.style.display = ''; }
  });
}

async function deleteBuildItem(section, idx) {
  const key = section === 'front' ? 'front_matter' : 'back_matter';
  const item = buildConfig[buildProfile][key][idx];
  if (!confirm(`Delete "${item.filename}"?\nThis will remove the file from disk.`)) return;
  const filename = item.filename;
  try {
    await apiFetch('DELETE', `/projects/${currentProject.id}/xhtml/${filename}`);
  } catch(e) { showStatus('build-status', '\u2717 ' + e.message, 'err'); return; }
  ['digital', 'print'].forEach(p => {
    ['front_matter', 'back_matter'].forEach(sec => {
      if (buildConfig[p]?.[sec]) {
        buildConfig[p][sec] = buildConfig[p][sec].filter(i => i.filename !== filename);
      }
    });
  });
  await saveBuildConfig();
  renderBuildPanel();
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
  
  
  const key      = section === 'front' ? 'front_matter' : 'back_matter';
  try {
    try {
      await apiFetch('GET', `/projects/${currentProject.id}/xhtml/${cleanFilename}`);
    } catch {
      try {
        const createData = await apiFetch('POST', `/projects/${currentProject.id}/xhtml/${cleanFilename}`);
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
  
  buildConfig[buildProfile][key].push({ filename: cleanFilename, type: 'custom' });
  await saveBuildConfig();
  renderBuildPanel();
  const item = buildConfig[buildProfile][key].slice(-1)[0];
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
  
  buildPreviewFile = filename;
  document.getElementById('build-preview-filename').textContent = filename;
  document.getElementById('btn-build-preview-edit').classList.remove('hidden');
  const body = document.getElementById('build-preview-body');
  const bodyParent = body?.parentElement;
  const bodyGrandparent = bodyParent?.parentElement;
  body.innerHTML = '<span style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">Loading…</span>';

  try {
    let data;
    try {
      data = await apiFetch('GET', `/projects/${currentProject.id}/xhtml/${filename}?t=${Date.now()}`);
    } catch {
      console.warn('previewBuildItem: file not found or error');
      body.innerHTML = `<p style="font-family:var(--mono);font-size:0.72rem;color:var(--accent)">⚠ File not found: ${escHtml(filename)}</p>`;
      document.getElementById('btn-build-preview-edit').classList.remove('hidden');
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
        if (preview.length >= PREVIEW_MAX_ELEMENTS) break;
        const text = el.textContent?.trim();
        if (text) {
          preview.push(`<${el.tagName.toLowerCase()}>${escHtml(text.substring(0, PREVIEW_MAX_CHARS))}${text.length > PREVIEW_MAX_CHARS ? '…' : ''}</${el.tagName.toLowerCase()}>`);
        }
      }
      const html = preview.length ? preview.join('<br/>') : '<p style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">(empty file)</p>';
      body.innerHTML = html;
      body.style.backgroundColor = '#F8F8FF';  // Yellow background for debugging
      body.style.color = '#000000';  // Black text for debugging
    } else {
      body.innerHTML = data.content;
    }
    
    const src      = data.source === 'global' ? '⚠ global template' : '✓ project file';
    const srcColor = data.source === 'global' ? 'var(--amber)' : 'var(--green)';
    document.getElementById('build-preview-filename').innerHTML =
      `${escHtml(filename)} <span style="color:${srcColor};font-size:0.6rem">${src}</span>`;
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
  if (!buildPreviewFile) {
    showStatus('build-status', '✗ No file selected in preview', 'err');
    return;
  }
  if (isDirty && currentChapterFile) {
    if (!confirm('You have unsaved changes. Discard them?')) return;
  }
  // Delegate to loadChapterList which will call openChapter — identical to a user click
  _pendingActiveFile = buildPreviewFile;
  showPanel('editor');
}
async function buildToc() {
  if (!currentProject) return;
  const btn = document.getElementById('btn-build-toc');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Building…';
  showStatus('build-action-status', 'Building TOC…', 'info');
  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/build-toc`);
    if (!data.ok) {
      showStatus('build-action-status', '✗ ' + (data.error || 'TOC build failed'), 'err'); return;
    }
    showStatus('build-action-status', `✓ TOC built — ${data.entries} entr${data.entries === 1 ? 'y' : 'ies'} inserted`, 'ok');
  } catch(e) { showStatus('build-action-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = '☰ Build TOC'; }
}