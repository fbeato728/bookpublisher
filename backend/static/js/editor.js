'use strict';

// ── Split panel ──────────────────────────────────────────────────────────────
async function loadFullXhtml() {
  const area = document.getElementById('split-text-area');
  area.innerHTML = '<div style="font-family:var(--mono);font-size:0.78rem;color:var(--text3);padding:2rem 0">Loading manuscript…</div>';
  splitElements = []; splitMarkers = [];
  updateSplitList();
  showStatus('split-status', '', '');

  // Check for existing chapter files and show warning banner
  try {
    let existingChapters = [];
    try { existingChapters = await apiFetch('GET', `/projects/${currentProject.id}/chapters`); } catch {}
    const banner = document.getElementById('split-existing-banner');
    if (existingChapters.length) {
      banner.style.display = '';
      banner.innerHTML = `<span>⚠ ${existingChapters.length} chapter file${existingChapters.length !== 1 ? 's' : ''} already exist — applying new splits will replace them.</span>
        <button class="btn danger" style="padding:0.2rem 0.6rem;font-size:0.72rem" onclick="deleteAllChapterFiles()">✕ Delete chapter files</button>`;
    } else {
      banner.style.display = 'none';
      banner.innerHTML = '';
    }
  } catch(e) { /* ignore */ }

  try {
    const data = await apiFetch('GET', `/projects/${currentProject.id}/full-xhtml`);
    const parser = new DOMParser();
    const doc    = parser.parseFromString(data.content, 'application/xhtml+xml');
    const body   = doc.querySelector('body');
    if (!body) { area.innerHTML = '<p style="color:var(--accent)">Could not parse XHTML body</p>'; return; }
    area.innerHTML = '';
    let idx = 0;
    for (const child of body.children) {
      const wrapper = document.createElement('div');
      wrapper.className = 'split-el';
      wrapper.dataset.index = idx;
      wrapper.innerHTML = child.outerHTML;
      const i = idx;
      wrapper.addEventListener('click', () => addSplitMarker(i, wrapper));
      area.appendChild(wrapper);
      splitElements.push(wrapper);
      idx++;
    }
    if (splitProjectId !== currentProject.id) {
      try {
        const stored = localStorage.getItem('splits:' + currentProject.id);
        splitSavedData = stored ? JSON.parse(stored) : [];
      } catch(e) { splitSavedData = []; }
      splitProjectId = currentProject.id;
    }
    splitSavedData.forEach(d => {
      const el = splitElements[d.beforeIndex];
      if (el) _insertMarkerDOM(d.beforeIndex, el, d.type, d.name);
    });
  } catch(e) {
    area.innerHTML = `<p style="color:var(--accent)">Error: ${e.message}</p>`;
  }
}

function _insertMarkerDOM(beforeIndex, wrapperEl, type, name) {
  const marker = document.createElement('div');
  marker.className = 'split-marker';
  marker.innerHTML = `
    <div class="split-marker-line"></div>
    <select class="marker-type">
      <option value="chapter">Chapter</option>
      <option value="part">Part</option>
      <option value="subchapter">Subchapter</option>
      <option value="record">Record</option>
      <option value="front">Front matter</option>
      <option value="back">Back matter</option>
    </select>
    <input class="marker-name" type="text" placeholder="Name / title…">
    <button class="split-marker-del" title="Remove">×</button>
  `;
  wrapperEl.parentNode.insertBefore(marker, wrapperEl);
  marker.querySelector('.marker-type').value = type || 'chapter';
  marker.querySelector('.marker-name').value = name || '';
  const obj = { beforeIndex, marker };
  splitMarkers.push(obj);
  marker.querySelector('.split-marker-del').addEventListener('click', e => {
    e.stopPropagation();
    marker.remove();
    splitMarkers = splitMarkers.filter(m => m !== obj);
    splitSavedData = splitSavedData.filter(d => d.beforeIndex !== beforeIndex);
    if (currentProject) localStorage.setItem('splits:' + currentProject.id, JSON.stringify(splitSavedData));
    updateSplitList();
  });
  marker.querySelector('.marker-type').addEventListener('change', () => syncSavedData());
  marker.querySelector('.marker-name').addEventListener('input',  () => syncSavedData());
  updateSplitList();
  return obj;
}

function syncSavedData() {
  splitSavedData = splitMarkers.map(m => ({
    beforeIndex: m.beforeIndex,
    type: m.marker.querySelector('.marker-type').value,
    name: m.marker.querySelector('.marker-name').value,
  }));
  if (currentProject) localStorage.setItem('splits:' + currentProject.id, JSON.stringify(splitSavedData));
  updateSplitList();
}

function addSplitMarker(beforeIndex, wrapperEl) {
  if (splitMarkers.find(m => m.beforeIndex === beforeIndex)) return;
  _insertMarkerDOM(beforeIndex, wrapperEl, 'chapter', '');
  syncSavedData();
  const last = splitMarkers[splitMarkers.length - 1];
  if (last) last.marker.querySelector('.marker-name').focus();
}

function updateSplitList() {
  const list = document.getElementById('split-list');
  document.getElementById('split-count').textContent = splitMarkers.length;
  if (!splitMarkers.length) {
    list.innerHTML = '<div class="split-list-empty">No splits yet.<br>Click in the text to add one.</div>'; return;
  }
  const sorted = [...splitMarkers].sort((a,b) => a.beforeIndex - b.beforeIndex);
  list.innerHTML = '';
  sorted.forEach(m => {
    const type = m.marker.querySelector('.marker-type').value;
    const name = m.marker.querySelector('.marker-name').value || '(unnamed)';
    const el   = document.createElement('div');
    el.className = 'split-list-item';
    el.innerHTML = `<span class="sli-type">${type}</span>${escHtml(name)}`;
    list.appendChild(el);
  });
}

function clearAllSplits() {
  splitMarkers.forEach(m => m.marker.remove());
  splitMarkers = []; splitSavedData = [];
  if (currentProject) localStorage.removeItem('splits:' + currentProject.id);
  updateSplitList();
}

async function deleteAllChapterFiles() {
  if (!currentProject) return;
  if (!confirm('Delete all chapter files from disk for this project? This cannot be undone.')) return;
  const banner = document.getElementById('split-existing-banner');
  banner.innerHTML = '<span>Deleting…</span>';
  try {
    const chapters = await apiFetch('GET', `/projects/${currentProject.id}/chapters`);
    let errors = 0;
    for (const ch of chapters) {
      try { await apiFetch('DELETE', `/projects/${currentProject.id}/chapters/${ch.filename}`); }
      catch { errors++; }
    }
    if (errors) {
      showStatus('split-status', `⚠ ${errors} file${errors !== 1 ? 's' : ''} could not be deleted`, 'err');
    } else {
      showStatus('split-status', `✓ ${chapters.length} chapter file${chapters.length !== 1 ? 's' : ''} deleted`, 'ok');
    }
    banner.style.display = 'none';
    banner.innerHTML = '';
    buildConfig = null; // force Build panel to reload
    loadBuildConfig();
  } catch(e) { showStatus('split-status', '✗ ' + e.message, 'err'); }
}

async function applySplits() {
  if (!splitMarkers.length) { showStatus('split-status', 'Add at least one split point first', 'err'); return; }
  const sorted = [...splitMarkers].sort((a,b) => a.beforeIndex - b.beforeIndex);
  const splits = sorted.map((m, i) => {
    const type = m.marker.querySelector('.marker-type').value;
    const name = m.marker.querySelector('.marker-name').value.trim() || `${type}-${i+1}`;
    const slug = name.toLowerCase().replace(/[^a-z0-9]/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'') || String(i+1);
    return { before_index: m.beforeIndex, type, name, filename: `${type}_${slug}` };
  });
  const btn = document.getElementById('btn-apply-splits');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Splitting…';
  showStatus('split-status', 'Generating chapter files…', 'info');
  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/split`, { splits });
    showStatus('split-status', `✓ ${data.saved.length} files created`, 'ok');
    currentProject.status = 'split'; currentProject.chapters = data.saved;
    // Fetch existing build config and update chapters in both profiles
    try {
      let bc = null;
      try { bc = await apiFetch('GET', `/projects/${currentProject.id}/build-config`); } catch {}
      if (bc) {
        const chapterEntries = data.saved.map(ch => ({ filename: ch.filename, enabled: true }));
        bc.digital.chapters = chapterEntries;
        bc.print.chapters   = chapterEntries;
        await apiFetch('POST', `/projects/${currentProject.id}/build-config`, bc);
      }
    } catch(e) { console.error('build-config update after split:', e); }
    buildConfig = null; // force Build panel to reload
    clearAllSplits();
    setTimeout(() => showPanel('editor'), 800);
  } catch(e) { showStatus('split-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = '✂ Apply splits'; }
}

document.getElementById('btn-apply-splits').addEventListener('click', applySplits);
document.getElementById('btn-clear-splits').addEventListener('click', clearAllSplits);


// ── Editor: file list ─────────────────────────────────────────────────────────
async function loadChapterList() {
  const list = document.getElementById('editor-filelist');
  list.innerHTML = '';
  try {
    // Load chapters
    const chapters = await apiFetch('GET', `/projects/${currentProject.id}/chapters`);

    // Load structural files (credits, taula, etc.)
    let allStructural = [];
    try { allStructural = await apiFetch('GET', `/projects/${currentProject.id}/xhtml`); } catch {}

    // Filter structural files to only those referenced in build config
    // so removing from build panel also removes from editor
    let bConfig = null;
    try { bConfig = await apiFetch('GET', `/projects/${currentProject.id}/build-config`); } catch {}
    let structural  = allStructural;
    if (bConfig) {
      const referenced = new Set();
      ['digital', 'print'].forEach(profile => {
        if (!bConfig[profile]) return;
        [...(bConfig[profile].front_matter || []),
         ...(bConfig[profile].back_matter  || [])].forEach(item => {
          // Handle both new format (filename) and old format (id)
          const fname = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : null);
          if (fname) referenced.add(fname);
        });
      });
      structural = allStructural.filter(f => referenced.has(f));
    }

    if (!chapters.length && !structural.length) {
      list.innerHTML = '<div style="padding:1rem;font-family:var(--mono);font-size:0.72rem;color:var(--text3)">No files yet.<br>Go to Split first.</div>';
      return;
    }
    if (structural.length) {
      const sep = document.createElement('div');
      sep.style.cssText = 'padding:0.4rem 1rem 0.2rem;font-family:var(--mono);font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border)';
      sep.textContent = 'Front / Back matter';
      list.appendChild(sep);
      structural.forEach(filename => {
        const el = document.createElement('div');
        el.className = 'editor-fileitem';
        el.textContent = filename;
        el.title = filename;
        el.onclick = () => openChapter(filename, el);
        list.appendChild(el);
      });
    }
    if (chapters.length) {
      const sep = document.createElement('div');
      sep.style.cssText = 'padding:0.4rem 1rem 0.2rem;font-family:var(--mono);font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border);margin-top:0.25rem';
      sep.textContent = 'Chapters';
      list.appendChild(sep);
      chapters.forEach(ch => {
        const el = document.createElement('div');
        el.className = 'editor-fileitem';
        el.textContent = ch.name || ch.filename;
        el.title = ch.filename;
        el.onclick = () => openChapter(ch.filename, el);
        list.appendChild(el);
      });
    }

    // CSS files section
    // Stylesheets section
    const cssSep = document.createElement('div');
    cssSep.style.cssText = 'padding:0.4rem 1rem 0.2rem;font-family:var(--mono);font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border);margin-top:0.25rem';
    cssSep.textContent = 'Stylesheets';
    list.appendChild(cssSep);

    // Standard CSS files (all global CSS)
    const standardCss = new Set(['digital.css', 'print.css', 'digital-credits.css', 'print-credits.css', 'book_big_title.css', 'taula.css']);
    
    // Add Standard label
    const stdLabel = document.createElement('div');
    stdLabel.style.cssText = 'padding:0.25rem 1rem 0.1rem 1rem;font-family:var(--mono);font-size:0.58rem;color:var(--text3);font-style:italic';
    stdLabel.textContent = 'Standard';
    list.appendChild(stdLabel);
    
    // Add all standard CSS files
    Array.from(standardCss).forEach(filename => {
      const el = document.createElement('div');
      el.className = 'editor-fileitem';
      el.textContent = filename;
      el.title = filename;
      el.onclick = () => openChapter(filename, el);
      list.appendChild(el);
    });

    // Custom CSS files from project styles dir (not in the standard set)
    try {
      const cssFiles  = await apiFetch('GET', `/projects/${currentProject.id}/styles`);
      {
        const customFiles = cssFiles.filter(f => !standardCss.has(f));
        if (customFiles.length) {
          const grpLabel = document.createElement('div');
          grpLabel.style.cssText = 'padding:0.25rem 1rem 0.1rem 1rem;font-family:var(--mono);font-size:0.58rem;color:var(--text3);font-style:italic';
          grpLabel.textContent = 'Custom';
          list.appendChild(grpLabel);
          customFiles.forEach(filename => {
            const el = document.createElement('div');
            el.className = 'editor-fileitem';
            el.textContent = filename;
            el.title = filename;
            el.onclick = () => openChapter(filename, el);
            list.appendChild(el);
          });
        }
      }
    } catch(e) { /* custom CSS listing is best-effort */ }

  } catch(e) { console.error('loadChapterList:', e); }
}

// ── Editor: open chapter ──────────────────────────────────────────────────────
async function openChapter(filename, listEl) {
  if (isDirty && currentChapterFile) {
    if (!confirm('You have unsaved changes. Discard them?')) return;
  }
  document.querySelectorAll('.editor-fileitem').forEach(e => e.classList.remove('active'));
  listEl?.classList.add('active');
  currentChapterFile = filename;
  document.getElementById('editor-filename').textContent = filename;
  setEditorStatus('Loading…', '');
  ltMatches = []; isDirty = false; fileIsHyphenated = false;

  // Chapters use /chapters/, CSS use /styles/, structural files use /xhtml/
  const isChapter = /^\d{4}_/.test(filename);
  const isCss     = filename.endsWith('.css');
  const path = isChapter ? `/projects/${currentProject.id}/chapters/${filename}`
             : isCss     ? `/projects/${currentProject.id}/styles/${filename}`
             :               `/projects/${currentProject.id}/xhtml/${filename}`;

  try {
    const data = await apiFetch('GET', path);

    if (isCss) {
      // CSS always opens in code mode with CSS syntax highlighting
      if (editorMode !== 'code') await switchToCodeMode();
      if (monacoEditor) {
        // Set CSS language on the model
        const model = monacoEditor.getModel();
        if (model) monaco.editor.setModelLanguage(model, 'css');
        monacoLoading = true;
        monacoEditor.setValue(data.content);
        monacoLoading = false;
        setTimeout(() => { isDirty = false; }, 0);
      }
      // Hide text-mode-only controls
      document.querySelectorAll('.lt-only').forEach(el => el.style.display = 'none');
      document.getElementById('btn-toggle-mode').style.display = 'none';
      document.getElementById('btn-preview-file').classList.add('hidden');
      if (previewVisible) togglePreviewPane();
      setEditorStatus(data.source === 'global' ? '⚠ Loaded from global — save to create project override' : '', data.source === 'global' ? 'warn' : '');
    } else {
      // Restore toggle button for XHTML files
      document.getElementById('btn-toggle-mode').style.display = '';
      document.getElementById('btn-preview-file').classList.remove('hidden');
      const parser = new DOMParser();
      const doc = parser.parseFromString(data.content, 'text/html');
      
      // Extract stylesheet href from loaded file
      const linkEl = doc.querySelector('link[rel="stylesheet"]');
      if (linkEl) {
        currentStylesheet = linkEl.getAttribute('href') || '../styles/main.css';
      } else {
        currentStylesheet = '../styles/main.css'; // fallback if no stylesheet found
      }
      
      const body   = doc.querySelector('body');
      let bodyHtmlLoad = body ? body.innerHTML : '';

      // Convert <!--fn:N--> or <!--fn:N:variant--> comments to visible fn-marker spans for text mode
      bodyHtmlLoad = bodyHtmlLoad.replace(/<!--fn:(\d+)(?::(\w+))?-->/g, (_, n, v) => {
        const variant = v || 'def';
        const label   = variant === 'def' ? `[fn:${n}]` : `[fn:${n}:${variant}]`;
        return `<span class="fn-marker" data-fn="${n}" data-variant="${variant}" contenteditable="false">${label}</span>`;
      });
      document.getElementById('editor-content').innerHTML = bodyHtmlLoad;

      if (editorMode === 'code' && monacoEditor) {
        // Restore XML language
        const model = monacoEditor.getModel();
        if (model) monaco.editor.setModelLanguage(model, 'xml');
        monacoLoading = true;
        monacoEditor.setValue(data.content);
        monacoLoading = false;
        setTimeout(() => { isDirty = false; }, 0);
      }
      document.getElementById('editor-content').dataset.rawXhtml = data.content;
      fileIsHyphenated = data.content.includes('\u00AD');
      setEditorStatus('', '');
      if (previewVisible) await refreshPreview();
    }
  } catch(e) { setEditorStatus('Error loading file', 'err'); }
}

// ── Preview pane ──────────────────────────────────────────────────────────────
let previewMode = 'digital';  // 'digital' or 'print'

function togglePreviewMode() {
  previewMode = previewMode === 'digital' ? 'print' : 'digital';
  const btn = document.getElementById('btn-preview-mode-toggle');
  btn.textContent = previewMode === 'digital' ? 'Digital | Print' : 'Digital | Print';
  btn.style.fontWeight = previewMode === 'print' ? 'bold' : 'normal';
  btn.style.textDecoration = previewMode === 'print' ? 'underline' : 'none';
  if (previewVisible) refreshPreview();
}
// currentStylesheet lives in globals.js (written from projects.js)

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
const debouncedRefreshPreview = debounce(() => { if (previewVisible) refreshPreview(); }, 500);

async function togglePreviewPane() {
  if (previewVisible) {
    previewVisible = false;
    document.getElementById('preview-pane').classList.remove('active');
    document.querySelector('.editor-layout').classList.remove('preview-open');
    document.getElementById('btn-preview-file').classList.remove('active-toggle');
  } else {
    previewVisible = true;
    document.querySelector('.editor-layout').classList.add('preview-open');
    document.getElementById('preview-pane').classList.add('active');
    document.getElementById('btn-preview-file').classList.add('active-toggle');
    await refreshPreview();
  }
}

async function refreshPreview() {
  if (!previewVisible || !currentProject || !currentChapterFile) return;

  // Get XHTML from editor
  let xhtml = '';
  if (editorMode === 'code' && monacoEditor) {
    xhtml = monacoEditor.getValue();
  } else {
    xhtml = serializeToXhtml();
  }

  // Parse XHTML
  const parser = new DOMParser();
  const doc = parser.parseFromString(xhtml, 'text/html');
  const body = doc.querySelector('body');
  
  if (!body) {
    document.getElementById('preview-pane-body').innerHTML = '<p style="color:red;font-family:monospace">Could not parse body</p>';
    return;
  }

  // Rewrite image URLs to API endpoints
  body.querySelectorAll('img').forEach(img => {
    const src = img.getAttribute('src') || '';
    const filename = src.split('/').pop();
    if (filename) {
      img.src = `/publisher/api/projects/${currentProject.id}/images/${filename}`;
    }
  });

  const pane = document.getElementById('preview-pane-body');
  
  // Remove old style tags
  const oldStyles = pane.parentNode.querySelectorAll('style');
  oldStyles.forEach(s => s.remove());

  // Inject body content
  pane.innerHTML = body.innerHTML;

  // Extract ALL stylesheet links from XHTML
  const linkEls = doc.querySelectorAll('link[rel="stylesheet"]');
  
  // Fetch and inject each stylesheet
  for (const linkEl of linkEls) {
    const href = linkEl.getAttribute('href');
    const cssFilename = href.split('/').pop();
    
    try {
      let cssData;
      try {
        cssData = await apiFetch('GET', `/projects/${currentProject.id}/styles/${cssFilename}`);
      } catch(cssErr) {
        console.warn(`CSS fetch failed for ${cssFilename}: ${cssErr.message}`);
        continue;
      }
      const cssContent = cssData.content || '';
      
      const styleEl = document.createElement('style');
      styleEl.textContent = cssContent;
      pane.parentNode.insertBefore(styleEl, pane);
    } catch(e) {
      console.error('Failed to load stylesheet:', cssFilename, e);
    }
  }

  // Now try to load and inject override CSS based on preview mode
  const overrideFilename = previewMode === 'print' ? 'print-overrides.css' : 'digital-overrides.css';
  
  try {
    let overrideData;
    try {
      overrideData = await apiFetch('GET', `/projects/${currentProject.id}/styles/${overrideFilename}`);
    } catch {
      return;
    }
    const overrideContent = overrideData.content || '';
    
    // Extract @media rules based on mode
    const mediaQuery = previewMode === 'print' ? '@media print' : '@media screen';
    const extractedRules = extractMediaRules(overrideContent, mediaQuery);
    
    if (extractedRules) {
      const styleEl = document.createElement('style');
      styleEl.textContent = extractedRules;
      pane.parentNode.insertBefore(styleEl, pane);
    } else {
    }
  } catch(e) {
    console.error('Failed to load override CSS:', overrideFilename, e);
  }
}

function extractMediaRules(cssContent, mediaQuery) {
  /**
   * Extract CSS rules from @media query block.
   * Example: @media print { ... } or @media screen { ... }
   * Returns the rules without the @media wrapper.
   */
  const regex = new RegExp(`@media\\s+${mediaQuery.replace('@media ', '')}\\s*\\{([^{}]*(?:\\{[^{}]*\\}[^{}]*)*)\\}`, 'i');
  const match = cssContent.match(regex);
  
  if (match && match[1]) {
    return match[1].trim();
  }
  return null;
}

// ── Editor: text/code toggle ──────────────────────────────────────────────────
document.getElementById('btn-toggle-mode').addEventListener('click', toggleEditorMode);

function toggleEditorMode() {
  if (editorMode === 'text') switchToCodeMode();
  else switchToTextMode();
}

function switchToCodeMode() {
  if (!currentChapterFile) return;
  // Use actual editor value if already in code mode, otherwise serialize from text mode
  const xhtml = (editorMode === 'code' && monacoEditor) ? monacoEditor.getValue() : serializeToXhtml();
  editorMode = 'code';
  document.getElementById('editor-scroll').classList.remove('active');
  document.getElementById('monaco-container').classList.add('active');
  document.getElementById('btn-toggle-mode').textContent = '¶ Text';
  document.getElementById('btn-toggle-mode').classList.add('active-toggle');
  document.getElementById('editor-mode-badge').textContent = 'CODE';
  document.getElementById('monaco-fs-control').style.display = 'flex';
  document.querySelectorAll('.lt-only').forEach(el => el.style.display = 'none');
  hideLtPopover();
  initMonaco(err => {
    if (err) { setEditorStatus('Monaco not available — check installation', 'err'); switchToTextMode(); return; }

  monaco.editor.defineTheme('pyteLight', {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'tag.xml', foreground: '007020', fontWeight: 'bold' },    // Keyword/Tag
      { token: 'tag', foreground: '007020', fontWeight: 'bold' },
      
      { token: 'attribute.name.xml', foreground: '7b5694' },             // Identifier/Attr
      { token: 'attribute.name', foreground: '7b5694' },
      
      { token: 'attribute.value.xml', foreground: '4070a0' },            // String/Value
      { token: 'string.xml', foreground: '4070a0' },
      { token: 'string', foreground: '4070a0' },
      
      { token: 'comment.xml', foreground: 'a0b0c0', fontStyle: 'italic' },
      { token: 'comment', foreground: 'a0b0c0', fontStyle: 'italic' },
      
      { token: 'metatag.xml', foreground: 'a07040' },                   // Constant/PreProc
    ],
    colors: {
      'editor.background': '#f0f0f0',           // pyte-light BG
      'editor.foreground': '#404850',           // pyte-light FG
      'editorLineNumber.background': '#8090a0', // LineNr BG
      'editorLineNumber.foreground': '#8090a0', // LineNr FG (white)
      'editor.lineHighlightBackground': '#F8DE7E55', // cursor_loc with transparency
    }
  });
    
  // --- 1. PLACE THE GLOBAL SETTING HERE ---
    // This tells the engine not to suggest standard XHTML namespaces
    monaco.languages.html.htmlDefaults.setOptions({
      suggest: { html5: false }
    });

    const container = document.getElementById('monaco-container');
    if (!monacoEditor) {
      monacoLoading = true;
      monacoEditor = monaco.editor.create(container, {
        value: xhtml, language: 'xml', theme: 'pyteLight', snippetSuggestions: 'none',
        fontSize: parseInt(localStorage.getItem(MONACO_FS_KEY)) || MONACO_FS_DEFAULT,
        fontFamily: "'IBM Plex Mono', monospace", lineNumbers: 'on',
        wordWrap: 'on', minimap: { enabled: false },
        scrollBeyondLastLine: false, automaticLayout: true,
      });
      monacoLoading = false;
      monacoEditor.onDidChangeModelContent(() => {
        if (!monacoLoading) {
          isDirty = true;
          debouncedRefreshPreview();
        }
      });
    } else {
      monacoLoading = true;
      monacoEditor.setValue(xhtml);
      monacoLoading = false;
      setTimeout(() => { isDirty = false; }, 0);
    }
  });
}

function switchToTextMode() {
  if (monacoEditor && editorMode === 'code') {
    const xhtml = monacoEditor.getValue();
    const parser = new DOMParser();
    const doc    = parser.parseFromString(xhtml, 'application/xhtml+xml');
    const body   = doc.querySelector('body');
    let bodyHtmlSwitch = body ? body.innerHTML : xhtml;
    bodyHtmlSwitch = bodyHtmlSwitch.replace(/<!--fn:(\d+)(?::(\w+))?-->/g, (_, n, v) => {
      const variant = v || 'def';
      const label   = variant === 'def' ? `[fn:${n}]` : `[fn:${n}:${variant}]`;
      return `<span class="fn-marker" data-fn="${n}" data-variant="${variant}" contenteditable="false">${label}</span>`;
    });
    document.getElementById('editor-content').innerHTML = bodyHtmlSwitch;
    ltMatches = [];
  }
  editorMode = 'text';
  document.getElementById('monaco-container').classList.remove('active');
  document.getElementById('editor-scroll').classList.add('active');
  document.getElementById('btn-toggle-mode').textContent = '⟨/⟩ Code';
  document.getElementById('btn-toggle-mode').classList.remove('active-toggle');
  document.getElementById('editor-mode-badge').textContent = 'TEXT';
  document.getElementById('monaco-fs-control').style.display = 'none';
  document.querySelectorAll('.lt-only').forEach(el => el.style.display = '');
  setEditorStatus('', '');
}

// ── Editor: save ─────────────────────────────────────────────────────────────
document.getElementById('btn-save-chapter').addEventListener('click', saveChapter);
document.addEventListener('keydown', e => {
  if ((e.ctrlKey||e.metaKey) && e.key==='s') { e.preventDefault(); saveChapter(); }
});

async function saveChapter() {
  if (!currentChapterFile) return;
  const xhtml = serializeToXhtml();
  const isChapter = /^\d{4}_/.test(currentChapterFile);
  const isCss     = currentChapterFile.endsWith('.css');
  const savePath = isChapter ? `/projects/${currentProject.id}/chapters/${currentChapterFile}`
                 : isCss     ? `/projects/${currentProject.id}/styles/${currentChapterFile}`
                 :               `/projects/${currentProject.id}/xhtml/${currentChapterFile}`;
  try {
    await apiFetch('PUT', savePath, { content: xhtml });
    // After save, extract the stylesheet from what was just saved
    if (!isCss) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(xhtml, 'application/xhtml+xml');
      const linkEl = doc.querySelector('link[rel="stylesheet"]');
      if (linkEl) {
        currentStylesheet = linkEl.getAttribute('href') || '../styles/main.css';
      }
    }
    isDirty = false;
    setEditorStatus('Saved ✓', 'ok');
    if (previewVisible) refreshPreview();

    // If this is a front/back matter file (not a chapter), refresh its Build preview
    // so changes immediately appear when user switches to Build panel
    if (!isChapter && !isCss && currentChapterFile) {
      const item = { filename: currentChapterFile };
      await previewBuildItem(item);
    }
  } catch(e) { setEditorStatus('Save failed: ' + e.message, 'err'); }
}

function serializeToXhtml() {
  if (editorMode === 'code' && monacoEditor) return monacoEditor.getValue();
  const editor = document.getElementById('editor-content');
  const clone  = editor.cloneNode(true);
  clone.querySelectorAll('.lt-err').forEach(span => {
    while (span.firstChild) span.parentNode.insertBefore(span.firstChild, span);
    span.remove();
  });
  // Convert fn-marker spans back to <!--fn:N--> or <!--fn:N:variant--> HTML comments
  clone.querySelectorAll('.fn-marker').forEach(span => {
    const n       = span.getAttribute('data-fn');
    const variant = span.getAttribute('data-variant') || 'def';
    const commentText = variant === 'def' ? `fn:${n}` : `fn:${n}:${variant}`;
    const comment = document.createComment(commentText);
    span.parentNode.replaceChild(comment, span);
  });
  // Comments survive cloneNode but innerHTML strips them — use XMLSerializer workaround
  let bodyHtml = clone.innerHTML.trim();
  // Remove xmlns attributes from child elements (keep only on root <html>)
  bodyHtml = bodyHtml.replace(/\s+xmlns(?::\w+)?="[^"]*"/g, '');
  // Re-insert comments: replace placeholder text (comments become empty in innerHTML on some browsers)
  // Safer: serialize via a temporary XML document
  bodyHtml = bodyHtml.replace(/\[fn:(\d+)(?::(\w+))?\]/g, (_, n, v) => {
    return v ? `<!--fn:${n}:${v}-->` : `<!--fn:${n}-->`;
  });
  return `<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <link rel="stylesheet" href="${currentStylesheet}" type="text/css"/>
    <title>${escHtml(currentProject?.title || 'Untitled')}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>
${bodyHtml}
  </body>
</html>`;
}

document.getElementById('editor-content').addEventListener('input', () => {
  isDirty = true;
  if (ltMatches.length) { ltMatches = []; setEditorStatus('Text edited — recheck to refresh marks', 'warn'); }
  debouncedRefreshPreview();
});

