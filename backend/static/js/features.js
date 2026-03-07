'use strict';

// ── LanguageTool ─────────────────────────────────────────────────────────────
function buildTextMap() {
  const editor = document.getElementById('editor-content');
  let text = ''; const nodes = [];
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const c = node.textContent.replace(/\u00a0/g,' ');
      nodes.push({ node, start: text.length, end: text.length + c.length });
      text += c; return;
    }
    if (node.nodeName==='BR') { text += '\n'; return; }
    const tag = node.nodeName.toLowerCase();
    const isBlock = ['p','div','li','h1','h2','h3','blockquote'].includes(tag);
    for (const child of node.childNodes) walk(child);
    if (isBlock && text.length && !text.endsWith('\n')) text += '\n';
  }
  for (const child of editor.childNodes) walk(child);
  return { text: text.replace(/\n+$/,''), nodes };
}

document.getElementById('btn-lt-check').addEventListener('click', checkGrammar);

async function checkGrammar() {
  if (checking || editorMode !== 'text') return;
  if (fileIsHyphenated) {
    if (!confirm('This file contains soft hyphens.\n\nGrammar check may produce false positives and miss real errors on hyphenated words.\n\nProceed anyway?')) return;
  }
  const { text } = buildTextMap();
  if (!text.trim()) return;
  checking = true;
  const btn = document.getElementById('btn-lt-check');
  btn.innerHTML = '<span class="spinner"></span> Checking'; btn.disabled = true;
  setEditorStatus('Checking grammar…', ''); hideLtPopover();
  try {
    const data = await apiFetch('POST', '/check', { text, language: document.getElementById('lt-lang').value, project_id: currentProject?.id || '' });
    if (data.error) { setEditorStatus('⚠ ' + data.error, 'err'); return; }
    ltMatches = Array.isArray(data) ? data : [];
    applyLtMarks(ltMatches);
    const n = ltMatches.length;
    setEditorStatus(n===0 ? '✓ No issues found' : `${n} issue${n!==1?'s':''} — click to fix`, n===0?'ok':'warn');
  } catch(e) { setEditorStatus('⚠ Server error', 'err'); }
  finally { checking=false; btn.textContent='Check grammar'; btn.disabled=false; }
}

function applyLtMarks(matches) {
  const editor = document.getElementById('editor-content');
  editor.querySelectorAll('.lt-err').forEach(span => {
    while (span.firstChild) span.parentNode.insertBefore(span.firstChild, span);
    span.remove();
  });
  editor.normalize();
  if (!matches.length) return;
  [...matches].sort((a,b)=>a.offset-b.offset).forEach((m,idx) => {
    const s=m.offset, e=s+m.length;
    // Store the surface text on the match for the ignore button
    const { text: fullText } = buildTextMap();
    m._surface = fullText.slice(s, e);
    const cat=(m.rule?.category?.id||'').toUpperCase(), it=m.rule?.issueType||'';
    const cls=(cat==='TYPOS'||cat==='SPELLING'||it==='misspelling')?'spell':(cat==='STYLE'||cat==='REDUNDANCY')?'style':'grammar';
    const { nodes } = buildTextMap();
    for (const tn of nodes) {
      if (tn.end<=s||tn.start>=e) continue;
      const os=Math.max(s,tn.start)-tn.start, oe=Math.min(e,tn.end)-tn.start;
      if (os>=oe) continue;
      let target=tn.node;
      if (os>0) target=tn.node.splitText(os);
      if (oe-os<target.length) target.splitText(oe-os);
      const span=document.createElement('span');
      span.className=`lt-err ${cls}`; span.dataset.idx=idx;
      target.parentNode.insertBefore(span,target); span.appendChild(target);
      break;
    }
  });
}

document.getElementById('editor-content').addEventListener('click', e => {
  const span = e.target.closest('.lt-err');
  if (!span) { hideLtPopover(); return; }
  e.stopPropagation();
  const match = ltMatches[parseInt(span.dataset.idx)];
  if (match) showLtPopover(span, match);
});

function showLtPopover(span, match) {
  document.querySelectorAll('.lt-err.active').forEach(s => s.classList.remove('active'));
  span.classList.add('active');
  document.getElementById('pop-rule').textContent = match.rule?.description || match.rule?.id || '';
  document.getElementById('pop-msg').textContent  = match.message || '';
  const box = document.getElementById('pop-suggs'); box.innerHTML = '';
  const repls = (match.replacements||[]).slice(0,6);
  if (!repls.length) box.innerHTML = '<span class="pop-no-sugg">No suggestions available</span>';
  else repls.forEach(r => {
    const btn = document.createElement('button'); btn.className='sugg-btn'; btn.textContent=r.value;
    btn.addEventListener('click', ex => { ex.stopPropagation(); applyLtFix(match,r.value); hideLtPopover(); });
    box.appendChild(btn);
  });
  // Show ignore button — store the matched surface text on the button
  const ignBtn = document.getElementById('pop-ignore-btn');
  const surface = match._surface || '';
  ignBtn.style.display = surface ? '' : 'none';
  ignBtn.textContent = `⊘ Ignore "${surface}" for this project`;
  const pop = document.getElementById('lt-popover'); pop.style.display='block';
  const rect=span.getBoundingClientRect(), pw=280, ph=pop.offsetHeight||100;
  let left=rect.left, top=rect.bottom+8, above=false;
  if (top+ph>window.innerHeight-12) { top=rect.top-ph-8; above=true; }
  if (left+pw>window.innerWidth-12) left=window.innerWidth-pw-12;
  if (left<8) left=8;
  pop.style.left=left+'px'; pop.style.top=top+'px'; pop.classList.toggle('above',above);
}

function hideLtPopover() {
  document.getElementById('lt-popover').style.display='none';
  document.querySelectorAll('.lt-err.active').forEach(s=>s.classList.remove('active'));
}

function applyLtFix(match, replacement) {
  const editor=document.getElementById('editor-content');
  const span=editor.querySelector(`.lt-err[data-idx="${ltMatches.indexOf(match)}"]`);
  if (span) { const tn=document.createTextNode(replacement); span.parentNode.replaceChild(tn,span); editor.normalize(); }
  const delta=replacement.length-match.length, e=match.offset+match.length;
  ltMatches=ltMatches.filter(m=>m!==match).map(m=>m.offset>=e?{...m,offset:m.offset+delta}:m);
  applyLtMarks(ltMatches); isDirty=true;
  const n=ltMatches.length;
  setEditorStatus(n===0?'✓ All issues resolved — remember to save':`${n} issue${n!==1?'s':''} remaining`, n===0?'ok':'warn');
}

document.addEventListener('click', e => {
  if (!document.getElementById('lt-popover').contains(e.target)) hideLtPopover();
});

// ── Font size control ────────────────────────────────────────────────────────
const FS_KEY = 'bp:fs-content';
const MONACO_FS_KEY = 'bp:fs-monaco';
const MONACO_FS_DEFAULT = 13;

function applyMonacoFontSize(px) {
  localStorage.setItem(MONACO_FS_KEY, px);
  if (monacoEditor) monacoEditor.updateOptions({ fontSize: px });
}

function applyFontSize(size) {
  document.documentElement.style.setProperty('--fs-content', size);
  document.querySelectorAll('.fs-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.size === size)
  );
  localStorage.setItem(FS_KEY, size);
}

document.querySelectorAll('.fs-btn').forEach(btn =>
  btn.addEventListener('click', () => applyFontSize(btn.dataset.size))
);

// ── Monaco font size ±  ───────────────────────────────────────────────────────
function updateMonacoFsLabel(px) {
  document.getElementById('monaco-fs-label').textContent = px + 'px';
}
document.getElementById('btn-monaco-fs-up').addEventListener('click', () => {
  const px = Math.min(24, (parseInt(localStorage.getItem(MONACO_FS_KEY)) || MONACO_FS_DEFAULT) + 1);
  applyMonacoFontSize(px); updateMonacoFsLabel(px);
});
document.getElementById('btn-monaco-fs-down').addEventListener('click', () => {
  const px = Math.max(10, (parseInt(localStorage.getItem(MONACO_FS_KEY)) || MONACO_FS_DEFAULT) - 1);
  applyMonacoFontSize(px); updateMonacoFsLabel(px);
});
updateMonacoFsLabel(parseInt(localStorage.getItem(MONACO_FS_KEY)) || MONACO_FS_DEFAULT);

// ── Preview font size ─────────────────────────────────────────────────────────
const PV_FS_KEY     = 'bp-preview-fs';
const PV_FS_DEFAULT = '0.95rem';

function applyPreviewFontSize(size) {
  document.getElementById('preview-pane-body').style.fontSize = size;
  document.querySelectorAll('.pv-fs-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.pvsize === size)
  );
  localStorage.setItem(PV_FS_KEY, size);
}

document.querySelectorAll('.pv-fs-btn').forEach(btn =>
  btn.addEventListener('click', () => applyPreviewFontSize(btn.dataset.pvsize))
);

applyPreviewFontSize(localStorage.getItem(PV_FS_KEY) || PV_FS_DEFAULT);


// ── Footnote manager ──────────────────────────────────────────────────────────
let projectFootnotes = [];
let projectFnVariants = [];   // e.g. ['one', 'two'] — 'def' is always implicit
let selectedFnVariant = 'def';  // active variant in insert dialog

async function loadFootnotes() {
  if (!currentProject) return;
  let data;
  try { data = await apiFetch('GET', `/projects/${currentProject.id}/footnotes`); }
  catch { return; }
  projectFootnotes = data.footnotes || [];
  // Also load variants from build-config if not already cached
  if (!buildConfig) {
    try { buildConfig = await apiFetch('GET', `/projects/${currentProject.id}/build-config`); }
    catch(e) { buildConfig = null; }
  }
  projectFnVariants = (buildConfig && buildConfig.fn_variants) || [];
  renderFnVariants();
  updateFootnoteUI();
}

function renderFnVariants() {
  const el = document.getElementById('fn-variants-list');
  if (!el) return;
  el.innerHTML = '';
  projectFnVariants.forEach(code => {
    const tag = document.createElement('span');
    tag.style.cssText = 'display:inline-flex;align-items:center;gap:0.3rem;' +
      'background:var(--surface2);border:1px solid var(--border2);border-radius:3px;' +
      'padding:0.15rem 0.5rem;font-family:var(--mono);font-size:0.75rem;color:var(--text2)';
    tag.innerHTML = `${code} <span style="cursor:pointer;color:var(--text3)" onclick="removeFnVariant('${code}')" title="Remove">✕</span>`;
    el.appendChild(tag);
  });
}

async function addFnVariant() {
  const input = document.getElementById('fn-variant-input');
  const code  = input.value.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!code || code === 'def' || projectFnVariants.includes(code)) { input.value = ''; return; }
  projectFnVariants.push(code);
  await saveFnVariants();
  renderFnVariants();
  input.value = '';
}

async function removeFnVariant(code) {
  projectFnVariants = projectFnVariants.filter(c => c !== code);
  await saveFnVariants();
  renderFnVariants();
}

async function saveFnVariants() {
  if (!currentProject || !buildConfig) return;
  buildConfig.fn_variants = projectFnVariants;
  await saveBuildConfig();
}

function updateFootnoteUI() {
  const hasFootnotes = projectFootnotes.length > 0;
  // Build panel: toggle collapsed/expanded
  const collapsed = document.getElementById('fn-card-collapsed');
  const expanded  = document.getElementById('fn-card-expanded');
  if (collapsed) collapsed.style.display = hasFootnotes ? 'none' : '';
  if (expanded)  expanded.style.display  = hasFootnotes ? '' : 'none';
  const status = document.getElementById('footnote-status');
  if (status) status.textContent = hasFootnotes ? `${projectFootnotes.length} footnotes loaded.` : '';
  // Editor toolbar: show fn button only when footnotes are loaded
  const fnBtn = document.getElementById('btn-insert-fn');
  if (fnBtn) fnBtn.style.display = hasFootnotes ? '' : 'none';
}

async function uploadFootnotes(input) {
  if (!input.files.length || !currentProject) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  let data;
  try { data = await apiFetch('POST', `/projects/${currentProject.id}/footnotes`, formData); }
  catch(e) { input.value = ''; alert(e.message || 'Upload failed'); return; }
  input.value = '';
  if (data.ok) {
    projectFootnotes = data.footnotes || [];
    updateFootnoteUI();
  } else {
    alert(data.error || 'Upload failed');
  }
}

async function deleteFootnotes() {
  if (!currentProject || !confirm('Remove footnotes from this project?')) return;
  try { await apiFetch('DELETE', `/projects/${currentProject.id}/footnotes`); } catch {}
  projectFootnotes = [];
  updateFootnoteUI();
}

function showFootnoteInsertDialog() {
  if (!projectFootnotes.length) {
    alert('No footnotes loaded. Upload a footnotes file in the Build panel first.');
    return;
  }
  // Save selection before dialog steals focus
  const sel = window.getSelection();
  window._savedFnRange = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;

  // Build variant selector if variants exist
  selectedFnVariant = 'def';
  const variantSelector = document.getElementById('fn-variant-selector');
  const variantButtons  = document.getElementById('fn-variant-buttons');
  if (projectFnVariants.length > 0) {
    variantButtons.innerHTML = '';
    ['def', ...projectFnVariants].forEach(code => {
      const btn = document.createElement('button');
      btn.className = code === 'def' ? 'btn active-toggle' : 'btn';
      btn.style.cssText = 'padding:0.25rem 0.6rem;font-size:0.75rem';
      btn.textContent = code;
      btn.onclick = () => {
        selectedFnVariant = code;
        variantButtons.querySelectorAll('.btn').forEach(b => {
          b.className = b.textContent === code ? 'btn active-toggle' : 'btn';
        });
      };
      variantButtons.appendChild(btn);
    });
    variantSelector.style.display = '';
  } else {
    variantSelector.style.display = 'none';
  }

  const list = document.getElementById('fn-dialog-list');
  list.innerHTML = '';
  projectFootnotes.forEach(fn => {
    const el = document.createElement('div');
    el.style.cssText = 'padding:0.35rem 0.5rem;border-radius:3px;cursor:pointer;font-size:0.78rem;' +
      'font-family:var(--mono);border:1px solid transparent';
    el.innerHTML = `<span style="color:var(--accent);margin-right:0.5rem">(${fn.n})</span>` +
      `<span style="color:var(--text2)">${fn.text.substring(0, 80)}${fn.text.length > 80 ? '…' : ''}</span>`;
    el.onmouseover = () => el.style.background = 'var(--surface2)';
    el.onmouseout  = () => el.style.background = '';
    el.onclick = () => insertFootnoteRef(fn.n, selectedFnVariant);
    list.appendChild(el);
  });

  document.getElementById('fn-dialog').style.display = 'block';
  document.getElementById('fn-dialog-overlay').style.display = 'block';
}

function closeFnDialog() {
  document.getElementById('fn-dialog').style.display = 'none';
  document.getElementById('fn-dialog-overlay').style.display = 'none';
}

function insertFootnoteRef(n, variant) {
  variant = variant || 'def';
  closeFnDialog();
  const markerText  = variant === 'def' ? `<!--fn:${n}-->` : `<!--fn:${n}:${variant}-->`;
  const labelText   = variant === 'def' ? `[fn:${n}]` : `[fn:${n}:${variant}]`;
  if (editorMode === 'code' && monacoEditor) {
    const sel = monacoEditor.getSelection();
    monacoEditor.executeEdits('fn', [{ range: sel, text: markerText }]);
  } else {
    const editor = document.getElementById('editor-content');
    editor.focus();
    if (window._savedFnRange) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(window._savedFnRange);
    }
    const span = document.createElement('span');
    span.className = 'fn-marker';
    span.setAttribute('data-fn', n);
    span.setAttribute('data-variant', variant);
    span.setAttribute('contenteditable', 'false');
    span.textContent = labelText;
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(span);
      range.setStartAfter(span);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }
  markDirty();
}

// ── Image manager ─────────────────────────────────────────────────────────────
async function loadImageList() {
  if (!currentProject) return;
  let data;
  try { data = await apiFetch('GET', `/projects/${currentProject.id}/images`); }
  catch { return; }
  renderImageList(data.images || [], {
    cover_image:          data.cover_image          || null,
    digital_inside_cover: data.digital_inside_cover || null,
    print_inside_cover:   data.print_inside_cover   || null,
  });
}

function renderImageList(images, covers) {
  const list = document.getElementById('image-list');
  if (!list) return;
  if (!images.length) {
    list.innerHTML = '<div style="font-family:var(--mono);font-size:0.72rem;color:var(--text3)">No images yet.</div>';
    return;
  }
  list.innerHTML = '';
  images.forEach(filename => {
    const isEpubCover    = filename === covers.cover_image;
    const isDigitalInside = filename === covers.digital_inside_cover;
    const isPrintInside   = filename === covers.print_inside_cover;
    const row = document.createElement('div');
    row.className = 'image-item';
    row.innerHTML = `
      <span class="image-item-name" title="${filename}">${filename}</span>
      <button class="image-cover-btn ${isEpubCover ? 'is-cover' : ''}"
        title="${isEpubCover ? 'EPUB cover (click to unset)' : 'Set as EPUB cover'}"
        onclick="setCoverImage('${filename}', 'cover_image', ${isEpubCover})">E</button>
      <button class="image-cover-btn ${isDigitalInside ? 'is-digital' : ''}"
        title="${isDigitalInside ? 'Digital inside cover (click to unset)' : 'Set as digital inside cover'}"
        onclick="setCoverImage('${filename}', 'digital_inside_cover', ${isDigitalInside})">D</button>
      <button class="image-cover-btn ${isPrintInside ? 'is-print' : ''}"
        title="${isPrintInside ? 'Print inside cover (click to unset)' : 'Set as print inside cover'}"
        onclick="setCoverImage('${filename}', 'print_inside_cover', ${isPrintInside})">P</button>
      <button class="image-del-btn" title="Delete" onclick="deleteImage('${filename}')">✕</button>
    `;
    list.appendChild(row);
  });
}

async function uploadImage(input) {
  if (!input.files.length || !currentProject) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  try { await apiFetch('POST', `/projects/${currentProject.id}/images`, formData); }
  catch {}
  input.value = '';
  loadImageList();
}

async function deleteImage(filename) {
  if (!confirm(`Delete ${filename}?`)) return;
  try { await apiFetch('DELETE', `/projects/${currentProject.id}/images/${filename}`); } catch {}
  loadImageList();
}

async function setCoverImage(filename, field, isAlreadySet) {
  const newVal = isAlreadySet ? null : filename;
  try { await apiFetch('PUT', `/projects/${currentProject.id}/cover-image`, { filename: newVal, field }); } catch {}
  loadImageList();
}

async function saveMetaField(field, value) {
  if (!currentProject) return;
  try {
    const data = await apiFetch('PATCH', `/projects/${currentProject.id}`, { [field]: value });
    currentProject = { ...currentProject, ...data.meta };
  } catch(e) { console.error('saveMetaField:', e); }
}

async function saveBuildConfig() {
  if (!currentProject || !buildConfig) return;
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/build-config`, buildConfig);
  } catch(e) { console.error('saveBuildConfig:', e); }
}

async function resetBuildConfig() {
  if (!confirm('Reset front and back matter for this profile to defaults? Chapters are kept. Files on disk are not deleted.')) return;
  const defaults = BUILD_DEFAULTS[buildProfile];
  buildConfig[buildProfile].front_matter = JSON.parse(JSON.stringify(defaults.front_matter));
  buildConfig[buildProfile].back_matter  = JSON.parse(JSON.stringify(defaults.back_matter));
  await saveBuildConfig();
  renderBuildPanel();
  showStatus('build-action-status', '↺ Reset to chapters only', 'info');
}

async function buildEpub() {
  if (!currentProject) return;
  const btn = document.getElementById('btn-build-epub');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Building…';
  showStatus('build-action-status', `Building ${buildProfile} EPUB…`, 'info');
  try {
    // binary response — not apiFetch
    const res = await fetch(`${API}/projects/${currentProject.id}/build/${buildProfile}`, { method: 'POST' });
    if (!res.ok) {
      const data = await res.json();
      showStatus('build-action-status', '✗ ' + (data.error || 'Build failed'), 'err'); return;
    }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; 
    a.download = `${currentProject.id}_${buildProfile}.epub`; 
    a.click();
    URL.revokeObjectURL(url);
    showStatus('build-action-status', `✓ ${buildProfile.charAt(0).toUpperCase() + buildProfile.slice(1)} EPUB downloaded`, 'ok');
  } catch(e) { showStatus('build-action-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = '↓ Build EPUB'; }
}

async function hyphenateChapters() {
  if (!currentProject) return;
  if (!confirm('This will insert soft hyphens into all content files for this project. Continue?')) return;
  const btn = document.getElementById('btn-hyphenate');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Hyphenating…';
  showStatus('build-action-status', 'Hyphenating chapters…', 'info');
  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/hyphenate`);
    if (!data.ok) {
      showStatus('build-action-status', '✗ ' + (data.error || 'Hyphenation failed'), 'err'); return;
    }
    const n   = data.processed.length;
    const err = data.errors.length;
    if (err) {
      showStatus('build-action-status',
        `⚠ ${n} file${n!==1?'s':''} hyphenated, ${err} error${err!==1?'s':''}`, 'err');
    } else {
      showStatus('build-action-status', `✓ ${n} file${n!==1?'s':''} hyphenated`, 'ok');
    }
    if (currentChapterFile && data.processed.includes(currentChapterFile)) {
      const activeEl = document.querySelector('.editor-fileitem.active');
      await openChapter(currentChapterFile, activeEl);
    }
  } catch(e) { showStatus('build-action-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = '⟳ Hyphenate chapters'; }
}

async function dehyphenateChapters() {
  if (!currentProject) return;
  if (!confirm('Remove all soft hyphens from content files?')) return;
  const btn = document.getElementById('btn-dehyphenate');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Removing…';
  showStatus('build-action-status', 'Removing soft hyphens…', 'info');
  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/dehyphenate`);
    if (!data.ok) {
      showStatus('build-action-status', '✗ ' + (data.error || 'Failed'), 'err'); return;
    }
    const n   = data.processed.length;
    const err = data.errors.length;
    if (err) {
      showStatus('build-action-status', `⚠ ${n} file${n!==1?'s':''} cleaned, ${err} error${err!==1?'s':''}`, 'err');
    } else {
      showStatus('build-action-status', `✓ ${n} file${n!==1?'s':''} dehyphenated`, 'ok');
    }
    // If the currently open file was dehyphenated, reload it so the editor
    // reflects the change and fileIsHyphenated is reset correctly
    if (currentChapterFile && data.processed.includes(currentChapterFile)) {
      const activeEl = document.querySelector('.editor-fileitem.active');
      await openChapter(currentChapterFile, activeEl);
    }
  } catch(e) { showStatus('build-action-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = '✕ Remove hyphens'; }
}

function markDirty() {
  isDirty = true;
}

// ── Text formatting ───────────────────────────────────────────────────────────
function applyFormat(tag) {
  if (editorMode === 'code' && monacoEditor) {
    // Code mode: wrap selection with tag
    const sel   = monacoEditor.getSelection();
    const model = monacoEditor.getModel();
    if (!sel || sel.isEmpty()) return;
    const selected = model.getValueInRange(sel);
    monacoEditor.executeEdits('format', [{
      range: sel,
      text: `<${tag}>${selected}</${tag}>`,
    }]);
    monacoEditor.focus();
    return;
  }
  // Text mode: execCommand then normalise tag
  // Browser uses <b>/<i> natively for bold/italic execCommand
  const cmd = tag === 'b' ? 'bold' : 'italic';
  document.execCommand(cmd, false, null);
  // execCommand may insert <strong>/<em> in some browsers — normalise to <b>/<i>
  const editor = document.getElementById('editor-content');
  editor.querySelectorAll('strong').forEach(el => {
    const b = document.createElement('b');
    while (el.firstChild) b.appendChild(el.firstChild);
    el.replaceWith(b);
  });
  editor.querySelectorAll('em').forEach(el => {
    const i = document.createElement('i');
    while (el.firstChild) i.appendChild(el.firstChild);
    el.replaceWith(i);
  });
  updateFormatButtons();
  isDirty = true;
}

function updateFormatButtons() {
  if (editorMode !== 'text') {
    document.getElementById('btn-bold').classList.remove('active');
    document.getElementById('btn-italic').classList.remove('active');
    return;
  }
  document.getElementById('btn-bold').classList.toggle('active',
    document.queryCommandState('bold'));
  document.getElementById('btn-italic').classList.toggle('active',
    document.queryCommandState('italic'));
}

document.getElementById('btn-bold').addEventListener('click',   () => applyFormat('b'));
document.getElementById('btn-italic').addEventListener('click', () => applyFormat('i'));

// Update active state on cursor move / selection change
document.getElementById('editor-content').addEventListener('keyup',   updateFormatButtons);
document.getElementById('editor-content').addEventListener('mouseup', updateFormatButtons);
document.getElementById('editor-content').addEventListener('selectionchange', updateFormatButtons);

// Ctrl+B / Ctrl+I — work in both modes
document.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (e.key === 'b') { e.preventDefault(); applyFormat('b'); }
  if (e.key === 'i') { e.preventDefault(); applyFormat('i'); }
});

// ── Ignore words ─────────────────────────────────────────────────────────────
let ignoreWords = [];

async function loadIgnoreWords() {
  if (!currentProject) return;
  try {
    ignoreWords = await apiFetch('GET', `/projects/${currentProject.id}/ignore-words`);
    renderIgnoreList();
  } catch(e) { console.error('loadIgnoreWords:', e); }
}

function renderIgnoreList() {
  const list = document.getElementById('ignore-list');
  if (!list) return;
  if (!ignoreWords.length) {
    list.innerHTML = '<div class="ignore-empty">No exceptions yet.<br>Click ⊘ in the grammar popover to add words.</div>';
    return;
  }
  list.innerHTML = '';
  ignoreWords.forEach(word => {
    const el = document.createElement('div');
    el.className = 'ignore-item';
    el.innerHTML = `<span>${escHtml(word)}</span><button class="ignore-del" title="Remove">×</button>`;
    el.querySelector('.ignore-del').addEventListener('click', () => removeIgnoreWord(word));
    list.appendChild(el);
  });
}

async function ignoreCurrentWord() {
  const btn = document.getElementById('pop-ignore-btn');
  // Extract word from button label: ⊘ Ignore "word" for this project
  const match = btn.textContent.match(/"([^"]+)"/);
  if (!match) return;
  const word = match[1];
  await addIgnoreWord(word);
  // Remove all marks for this word from the current check
  ltMatches = ltMatches.filter(m => (m._surface || '').toLowerCase() !== word.toLowerCase());
  applyLtMarks(ltMatches);
  const n = ltMatches.length;
  setEditorStatus(n === 0 ? '✓ All issues resolved' : `${n} issue${n!==1?'s':''} remaining`, n === 0 ? 'ok' : 'warn');
  hideLtPopover();
}

async function addIgnoreWord(word) {
  if (!currentProject) return;
  try {
    await apiFetch('POST', `/projects/${currentProject.id}/ignore-words`, { word });
    await loadIgnoreWords();
  } catch(e) { console.error('addIgnoreWord:', e); }
}

async function removeIgnoreWord(word) {
  if (!currentProject) return;
  try {
    await apiFetch('DELETE', `/projects/${currentProject.id}/ignore-words/${encodeURIComponent(word)}`);
    await loadIgnoreWords();
  } catch(e) { console.error('removeIgnoreWord:', e); }
}

function toggleIgnorePanel() {
  const panel = document.getElementById('ignore-panel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) loadIgnoreWords();
}

// ── Boot ──────────────────────────────────────────────────────────────────────
applyFontSize(localStorage.getItem(FS_KEY) || '1rem');
loadProjects();
