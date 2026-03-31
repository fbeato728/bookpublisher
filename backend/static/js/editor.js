'use strict';

// ── Dirty check modal ─────────────────────────────────────────────────────────
// Returns a promise resolving to 'save', 'discard', or 'cancel'
function confirmIfDirty() {
  if (!isDirty || !currentChapterFile) return Promise.resolve('discard');
  return new Promise(resolve => {
    document.getElementById('dirty-dialog-filename').textContent = currentChapterFile;
    document.getElementById('dirty-dialog').classList.remove('hidden');
    document.getElementById('dirty-dialog-overlay').classList.remove('hidden');

    const close = result => {
      document.getElementById('dirty-dialog').classList.add('hidden');
      document.getElementById('dirty-dialog-overlay').classList.add('hidden');
      resolve(result);
    };

    document.getElementById('dirty-btn-save').onclick    = () => saveChapter().then(() => close('save'));
    document.getElementById('dirty-btn-discard').onclick = () => close('discard');
    document.getElementById('dirty-btn-cancel').onclick  = () => close('cancel');
    document.getElementById('dirty-dialog-overlay').onclick = () => close('cancel');
  });
}

// Declared here as fallback if not in globals.js
// if (typeof _pendingActiveFile === 'undefined') var _pendingActiveFile = null;

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

    function _getFileBadge(filename) {
      if (!bConfig) return '';
      let inDigital = false, inPrint = false;
      ['front_matter', 'back_matter'].forEach(sec => {
        (bConfig.digital?.[sec] || []).forEach(item => {
          const f = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : null);
          if (f === filename) inDigital = true;
        });
        (bConfig.print?.[sec] || []).forEach(item => {
          const f = item.filename || (item.id ? (item.id.endsWith('.xhtml') ? item.id : item.id + '.xhtml') : null);
          if (f === filename) inPrint = true;
        });
      });
      if (inDigital && inPrint) return 'B';
      if (inDigital) return 'D';
      if (inPrint)   return 'P';
      return '';
    }

    function _makeFileItem(text, title, onclick, badge) {
      const el = document.createElement('div');
      el.className = 'editor-fileitem';
      el.title = title;
      el.onclick = onclick;
      const label = document.createElement('span');
      label.className = 'editor-fileitem-label';
      label.textContent = text;
      el.appendChild(label);
      if (badge) {
        const b = document.createElement('span');
        b.className = 'editor-fileitem-badge';
        b.textContent = badge;
        el.appendChild(b);
      }
      return el;
    }

    if (structural.length) {
      const sep = document.createElement('div');
      sep.style.cssText = 'padding:0.4rem 1rem 0.2rem;font-family:var(--mono);font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border)';
      sep.textContent = 'Front / Back matter';
      list.appendChild(sep);
      structural.forEach(filename => {
        const el = _makeFileItem(filename, filename, () => openChapter(filename, el), _getFileBadge(filename));
        list.appendChild(el);
      });
    }
    if (chapters.length) {
      const sep = document.createElement('div');
      sep.style.cssText = 'padding:0.4rem 1rem 0.2rem;font-family:var(--mono);font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border);margin-top:0.25rem';
      sep.textContent = 'Chapters';
      list.appendChild(sep);
      chapters.forEach(ch => {
        const el = _makeFileItem(ch.filename, ch.filename, () => openChapter(ch.filename, el), 'B');
        list.appendChild(el);
      });
    }

    // Stylesheets section
    const cssSep = document.createElement('div');
    cssSep.style.cssText = 'padding:0.4rem 1rem 0.2rem;font-family:var(--mono);font-size:0.6rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border);margin-top:0.25rem';
    cssSep.textContent = 'Stylesheets';
    list.appendChild(cssSep);

    try {
      const [globalCss, projectCss] = await Promise.all([
        apiFetch('GET', '/global/styles'),
        apiFetch('GET', `/projects/${currentProject.id}/styles`).catch(() => [])
      ]);
      const standardCss = new Set(globalCss);
      const customFiles = projectCss.filter(f => !standardCss.has(f));

      if (globalCss.length) {
        const stdLabel = document.createElement('div');
        stdLabel.style.cssText = 'padding:0.25rem 1rem 0.1rem 1rem;font-family:var(--mono);font-size:0.58rem;color:var(--text3);font-style:italic';
        stdLabel.textContent = 'Standard';
        list.appendChild(stdLabel);
        globalCss.forEach(filename => {
          const el = document.createElement('div');
          el.className = 'editor-fileitem';
          el.textContent = filename;
          el.title = filename;
          el.onclick = () => openChapter(filename, el);
          list.appendChild(el);
        });
      }

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
    } catch(e) { /* CSS listing is best-effort */ }

  } catch(e) { console.error('loadChapterList:', e); }

  // Open file from build panel — identical to user clicking it in the list
  if (typeof _pendingActiveFile !== 'undefined' && _pendingActiveFile) {
    const target = _pendingActiveFile;
    _pendingActiveFile = null;
    const el = [...document.querySelectorAll('.editor-fileitem')].find(e => e.title === target || e.textContent === target);
    if (el) openChapter(target, el);
  }
}

// ── Editor: open chapter ──────────────────────────────────────────────────────
async function openChapter(filename, listEl) {
  if (isDirty && currentChapterFile) {
    const result = await confirmIfDirty();
    if (result === 'cancel') return;
    // 'save' was handled inside confirmIfDirty, 'discard' falls through
  }
  document.querySelectorAll('.editor-fileitem').forEach(e => e.classList.remove('active'));
  listEl?.classList.add('active');
  currentChapterFile = filename;
  document.getElementById('editor-filename').textContent = filename;
  setEditorStatus('Loading…', '');
  ltMatches = []; isDirty = false; fileIsHyphenated = false;

  // Reset scroll state for both preview pane and Monaco editor
  const pvBody = document.getElementById('preview-pane-body');
  if (pvBody) pvBody.scrollTop = 0;
  if (monacoEditor) monacoEditor.revealLine(1);

  // Chapters use /chapters/, CSS use /styles/, structural files use /xhtml/
  const isChapter = /^\d{4}_/.test(filename);
  const isCss     = filename.endsWith('.css');
  const path = isChapter ? `/projects/${currentProject.id}/chapters/${filename}`
             : isCss     ? `/projects/${currentProject.id}/styles/${filename}`
             :               `/projects/${currentProject.id}/xhtml/${filename}`;

  try {
    const data = await apiFetch('GET', path);

    if (isCss) {
      // CSS always opens in code mode - switchToCodeMode handles all initialization
      editorMode = 'code';
      // await switchToCodeMode();
      await switchToCodeMode(data.content);
      if (monacoEditor) { const model = monacoEditor.getModel(); if (model) monaco.editor.setModelLanguage(model, 'css'); }
      // if (monacoEditor) {
      //   const model = monacoEditor.getModel();
      //   if (model) monaco.editor.setModelLanguage(model, 'css');
      //   monacoLoading = true;
      //   monacoEditor.setValue(data.content);
      //   monacoLoading = false;
      //   setTimeout(() => { isDirty = false; }, 0);
      // }
      
      // CHANGED (STEP 11): Ensure preview always visible
      if (!previewVisible) {
        previewVisible = true;
        document.querySelector('.editor-layout').classList.add('preview-open');
        document.getElementById('preview-pane').classList.add('active');
      }
      await loadPreviewStyles();
      await refreshPreview();
      
      setEditorStatus(data.source === 'global' ? '⚠ Loaded from global — save to create project override' : '', data.source === 'global' ? 'warn' : '');
      loadCssTokenStrip();
    } else {
      // XHTML files: Always open in code mode - switchToCodeMode handles all initialization
      editorMode = 'code';
      // await switchToCodeMode();
      await switchToCodeMode(data.content);
      if (monacoEditor) { const model = monacoEditor.getModel(); if (model) monaco.editor.setModelLanguage(model, 'xml'); }

      // Parse XHTML to extract stylesheet reference for preview
      const parser = new DOMParser();
      const doc = parser.parseFromString(data.content, 'text/html');
      
      // Extract stylesheet href from loaded file
      const linkEl = doc.querySelector('link[rel="stylesheet"]');
      if (linkEl) {
        currentStylesheet = linkEl.getAttribute('href') || '../styles/main.css';
      } else {
        currentStylesheet = '../styles/main.css'; // fallback if no stylesheet found
      }
      
      fileIsHyphenated = data.content.includes('\u00AD');
      
      setEditorStatus('', '');
      
      // CHANGED (STEP 11): Ensure preview always visible
      if (!previewVisible) {
        previewVisible = true;
        document.querySelector('.editor-layout').classList.add('preview-open');
        document.getElementById('preview-pane').classList.add('active');
      }
      await loadPreviewStyles();
      await refreshPreview();
      loadCssTokenStrip();
    }
  } catch(e) { setEditorStatus('Error loading file', 'err'); }
}

// ── Preview pane ──────────────────────────────────────────────────────────────
let previewMode = 'digital';  // 'digital' or 'print'

async function togglePreviewMode() {
  previewMode = previewMode === 'digital' ? 'print' : 'digital';
  const btn = document.getElementById('btn-preview-mode-toggle');
  btn.classList.toggle('mode-digital');
  btn.classList.toggle('mode-print');

  if (previewVisible) {
    cachedStyles = {};
    // BLINK FIX: await styles fully built before touching content —
    // previously these fired concurrently, leaving a gap where styles
    // were gone but new content was already visible.
    await loadPreviewStyles();
    await refreshPreview();
  }
  loadCssTokenStrip();
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
    // document.getElementById('btn-preview-file').classList.remove('active-toggle');
  } else {
    previewVisible = true;
    document.querySelector('.editor-layout').classList.add('preview-open');
    document.getElementById('preview-pane').classList.add('active');
    // document.getElementById('btn-preview-file').classList.add('active-toggle');
    // await refreshPreview();
    await loadPreviewStyles();
    await refreshPreview();
  }
}

// ── Token substitution cache ──────────────────────────────────────────────────
let _tokensJsonCache  = null;
let _cssTokensCache   = null;
let _cssTokensProject = null;
let _fnMapCache      = null;
let _fnMapProjectId  = null;

async function _getCssTokens() {
  if (_cssTokensCache && _cssTokensProject === currentProject?.id) return _cssTokensCache;
  try {
    const data = await apiFetch('GET', `/projects/${currentProject.id}/css-tokens`);
    _cssTokensCache   = {};
    _cssTokensProject = currentProject.id;
    for (const [token, cfg] of Object.entries(data)) {
      _cssTokensCache[token] = cfg.value || cfg.default || '';
    }
  } catch { _cssTokensCache = {}; _cssTokensProject = currentProject?.id; }
  return _cssTokensCache;
}

function _applyCssTokens(css, tokens) {
  for (const [token, value] of Object.entries(tokens)) {
    css = css.replaceAll(token, value);
  }
  return css;
}

function invalidateCssTokensCache() {
  _cssTokensCache   = null;
  _cssTokensProject = null;
  cachedStyles      = {};  // also clear CSS cache so preview re-fetches
}

async function _getFnMap() {
  if (_fnMapCache && _fnMapProjectId === currentProject?.id) return _fnMapCache;
  try {
    const data = await apiFetch('GET', `/projects/${currentProject.id}/footnotes/map`);
    _fnMapCache     = {};
    _fnMapProjectId = currentProject.id;
    (data.footnotes || []).forEach(fn => { _fnMapCache[fn.id] = fn.content || ''; });
  } catch { _fnMapCache = {}; _fnMapProjectId = currentProject?.id; }
  return _fnMapCache;
}

async function _getTokensJson() {
  if (_tokensJsonCache) return _tokensJsonCache;
  try {
    const data = await apiFetch('GET', '/config/tokens');
    _tokensJsonCache = data;
  } catch(e) {
    _tokensJsonCache = {};
  }
  return _tokensJsonCache;
}

async function _substituteTokens(xhtml) {
  if (!xhtml.includes('{{')) return xhtml;
  const tokensJson = await _getTokensJson();
  const meta = currentProject || {};
  for (const [token, cfg] of Object.entries(tokensJson)) {
    let value = cfg.default || '';
    if (cfg.meta_field) {
      value = meta[cfg.meta_field] ?? value;
    } else if (cfg.meta_fields) {
      for (const f of cfg.meta_fields) {
        if (meta[f]) { value = meta[f]; break; }
      }
    }
    xhtml = xhtml.replaceAll(token, value);
  }
  return xhtml;
}

async function refreshPreview() {
  if (!previewVisible || !currentProject || !currentChapterFile) return;

  // STOP: If we are in a CSS file, do not touch the HTML content of the preview
  if (currentChapterFile.endsWith('.css')) return; 

  let xhtml = '';
  if (monacoEditor) {
    xhtml = monacoEditor.getValue();
  } else {
    return;
  }

  // Substitute tokens client-side from tokens.json + project meta
  if (xhtml.includes('{{')) {
    xhtml = await _substituteTokens(xhtml);
  }

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
  
  // ← ONLY update body content, do NOT remove/re-add styles
  pane.innerHTML = body.innerHTML;

  // Enrich fn-marker spans with footnote content as custom HTML tooltip
  const fnSpans = pane.querySelectorAll('.fn-marker');
  if (fnSpans.length) {
    const fnMap = await _getFnMap();
    fnSpans.forEach(span => {
      const id = span.getAttribute('data-fn');
      if (!id || !fnMap[id]) return;
      const num     = span.getAttribute('data-display');
      const content = fnMap[id];
      span.title = ''; // clear any native tooltip
      span.addEventListener('mouseenter', e => {
        const tip = document.createElement('div');
        tip.id = 'fn-hover-tip';
        tip.style.cssText = `
          position:fixed;
          z-index:9999;
          max-width:320px;
          background:var(--bg2,#1e1e2e);
          color:var(--text1,#cdd6f4);
          border:1px solid var(--border,#45475a);
          border-radius:5px;
          padding:0.4rem 0.6rem;
          font-family:var(--sans,'Inter',sans-serif);
          font-size:0.78rem;
          line-height:1.5;
          pointer-events:none;
          box-shadow:0 4px 16px rgba(0,0,0,0.4);
        `;
        tip.innerHTML = `<span style="opacity:0.5;font-size:0.7rem">[${num}]</span> ${content}`;
        document.body.appendChild(tip);
        // Position near cursor
        const x = Math.min(e.clientX + 12, window.innerWidth  - 340);
        const y = Math.min(e.clientY + 16, window.innerHeight - 80);
        tip.style.left = x + 'px';
        tip.style.top  = y + 'px';
      });
      span.addEventListener('mousemove', e => {
        const tip = document.getElementById('fn-hover-tip');
        if (!tip) return;
        const x = Math.min(e.clientX + 12, window.innerWidth  - 340);
        const y = Math.min(e.clientY + 16, window.innerHeight - 80);
        tip.style.left = x + 'px';
        tip.style.top  = y + 'px';
      });
      span.addEventListener('mouseleave', () => {
        const tip = document.getElementById('fn-hover-tip');
        if (tip) tip.remove();
      });
    });
  }

  if (ltMatches && ltMatches.length) applyLtMarks(ltMatches);
}

async function loadPreviewStyles() {
  const pane     = document.getElementById('preview-pane-body');
  const container = pane.parentNode;

  // BLINK FIX: Collect all new <style> elements into a fragment BEFORE
  // touching the DOM. Old styles remain live the entire time async fetches
  // run — there is never a moment where styles are gone and content is visible.
  const fragment = document.createDocumentFragment();

  // Helper: build a <style> element with token substitution applied
  function _makeStyleEl(css, tokens) {
    const el = document.createElement('style');
    el.textContent = _applyCssTokens(css, tokens);
    return el;
  }

  // ── Resolve which stylesheet hrefs this file needs ────────────────────────
  let stylesheetHrefs = [];
  if (!currentChapterFile.endsWith('.css')) {
    // XHTML file: parse <link> tags from Monaco content and remember them
    const xhtml  = monacoEditor ? monacoEditor.getValue() : '';
    const parser = new DOMParser();
    const doc    = parser.parseFromString(xhtml, 'text/html');
    const linkEls = Array.from(doc.querySelectorAll('link[rel="stylesheet"]'));
    lastXhtmlStylesheets = linkEls.map(l => l.getAttribute('href'));
    stylesheetHrefs = lastXhtmlStylesheets;
  } else {
    // CSS file: use the hrefs we remembered from the last XHTML that was open
    stylesheetHrefs = lastXhtmlStylesheets;
  }

  // ── Fetch CSS tokens once — used for substitution on every style block ────
  const cssTokens = await _getCssTokens();

  // ── Build <style> elements for each linked stylesheet ────────────────────
  for (const href of stylesheetHrefs) {
    const cssFilename = href.split('/').pop();

    if (currentChapterFile === cssFilename && monacoEditor) {
      // Editing this exact CSS file live — use Monaco content directly
      fragment.appendChild(_makeStyleEl(monacoEditor.getValue(), cssTokens));
      continue;
    }

    if (cachedStyles[cssFilename]) {
      // Cache hit — no network round-trip needed
      fragment.appendChild(_makeStyleEl(cachedStyles[cssFilename], cssTokens));
    } else {
      try {
        // Cache miss — fetch once, store, then build element
        const cssData = await apiFetch('GET', `/projects/${currentProject.id}/styles/${cssFilename}`);
        cachedStyles[cssFilename] = cssData.content || '';
        fragment.appendChild(_makeStyleEl(cachedStyles[cssFilename], cssTokens));
      } catch(e) { console.warn(`CSS fetch failed: ${cssFilename}`); }
    }
  }

  // ── Build <style> element for the profile override ───────────────────────
  const overrideFilename = previewMode === 'print' ? 'print-overrides.css' : 'digital-overrides.css';
  try {
    let overrideContent = '';

    if (currentChapterFile === overrideFilename && monacoEditor) {
      // Editing the override file itself — use Monaco content live
      overrideContent = monacoEditor.getValue();
    } else if (cachedStyles[overrideFilename]) {
      // Already extracted and cached — use directly, no re-extraction needed
      fragment.appendChild(_makeStyleEl(cachedStyles[overrideFilename], cssTokens));
      overrideContent = ''; // signal: nothing left to extract below
    } else {
      // Fetch and extract the relevant @media block
      const overrideData = await apiFetch('GET', `/projects/${currentProject.id}/styles/${overrideFilename}`);
      overrideContent = overrideData.content || '';
    }

    if (overrideContent) {
      const strippedContent = overrideContent.replace(/\/\*[\s\S]*?\*\//g, '');
      const mediaQuery      = previewMode === 'print' ? '@media print' : '@media screen';
      const extractedRules  = extractMediaRules(strippedContent, mediaQuery);
      if (extractedRules) {
        // Cache extracted rules (only when not live-editing the override)
        if (currentChapterFile !== overrideFilename) {
          cachedStyles[overrideFilename] = extractedRules;
        }
        fragment.appendChild(_makeStyleEl(extractedRules, cssTokens));
      }
    }
  } catch(e) {
    console.error('Failed to load override CSS:', overrideFilename, e);
  }

  // ── Atomic DOM swap ───────────────────────────────────────────────────────
  // All async work is done. Now remove old styles and insert new ones in a
  // single synchronous pass — the browser paints once, no intermediate state.
  container.querySelectorAll('style').forEach(s => s.remove());
  container.insertBefore(fragment, pane);
}

// ── CSS Token Strip ───────────────────────────────────────────────────────────
// Default steps by unit — used when token has no step defined
const _CSS_STRIP_STEPS = { 'em': 0.1, '%': 1, 'px': 1 };

async function loadCssTokenStrip() {
  const strip = document.getElementById('css-token-strip');
  if (!strip || !currentProject || !currentChapterFile) { if (strip) strip.style.display = 'none'; return; }

  const tokens = await apiFetch('GET', `/projects/${currentProject.id}/css-tokens`);
  if (!tokens || !Object.keys(tokens).length) { strip.style.display = 'none'; return; }

  // Scan current file content for class names and linked CSS files
  const content = monacoEditor ? monacoEditor.getValue() : '';
  const fileClasses = new Set((content.match(/class="([^"]+)"/g) || [])
    .flatMap(m => m.replace(/class="|"/g, '').split(/\s+/)));

  // Extract CSS filenames referenced in <link> tags of this file
  // Also always include override files since they're loaded globally
  const linkedCss = new Set((content.match(/href="([^"]+\.css)"/g) || [])
    .map(m => m.replace(/href="|"/g, '').split('/').pop()));
  linkedCss.add('print-overrides.css');
  linkedCss.add('digital-overrides.css');

  // Filter tokens by: css_file linked in this file + class match + profile
  const matching = Object.entries(tokens).filter(([, cfg]) => {
    // Token's CSS file must be linked in this XHTML file (or be an override)
    if (cfg.css_file && !linkedCss.has(cfg.css_file)) return false;
    const classes = cfg.classes || [];
    if (classes.length && !classes.some(c => fileClasses.has(c))) return false;
    const profile = cfg.profile || 'both';
    if (profile === 'both') return true;
    return profile === previewMode;
  });

  if (!matching.length) { strip.style.display = 'none'; return; }

  strip.innerHTML = '';
  strip.style.display = 'flex';

  matching.forEach(([token, cfg]) => {
    const val     = cfg.value || cfg.default || '';
    const numMatch = val.match(/^([\d.]+)([a-z%]*)$/);
    const num     = numMatch ? parseFloat(numMatch[1]) : null;
    const unit    = numMatch ? numMatch[2] : '';
    const step    = cfg.step != null ? cfg.step : (_CSS_STRIP_STEPS[unit] || 0.1);

    const ctrl = document.createElement('div');
    ctrl.className = 'css-strip-token';
    ctrl.innerHTML = `
      <span class="css-strip-label">${escHtml(cfg.label)}</span>
      <button class="css-strip-btn" data-dir="-1">−</button>
      <span class="css-strip-value">${escHtml(val)}</span>
      <button class="css-strip-btn" data-dir="1">+</button>
    `;
    strip.appendChild(ctrl);

    const valEl = ctrl.querySelector('.css-strip-value');
    ctrl.querySelectorAll('.css-strip-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const dir     = parseInt(btn.dataset.dir);
        const current = valEl.textContent.trim();
        const m       = current.match(/^([\d.]+)([a-z%]*)$/);
        if (!m || num === null) return;
        const newNum  = Math.max(0, parseFloat(m[1]) + dir * step);
        const newVal  = parseFloat(newNum.toFixed(4)).toString() + (m[2] || unit);
        valEl.textContent = newVal;
        cfg.value = newVal;
        try {
          await apiFetch('PUT', `/projects/${currentProject.id}/css-tokens`, { [token]: newVal });
          if (typeof invalidateCssTokensCache === 'function') invalidateCssTokensCache();
          // BLINK FIX: await both calls — styles must be fully swapped in
          // before content repaints, same pattern as togglePreviewMode.
          if (previewVisible) await loadPreviewStyles();
          if (previewVisible) await refreshPreview();
        } catch(e) { console.error('css-strip save:', e); }
      });
    });
  });
}

function extractMediaRules(cssContent, mediaQuery) {
  const keyword = mediaQuery.replace('@media ', '').trim();
  const re = new RegExp('@media\\s+' + keyword + '\\s*\\{', 'i');
  const match = re.exec(cssContent);
  if (!match) return null;

  // Start just after the opening { of @media block
  const start = match.index + match[0].length;
  let depth = 1;
  let end   = -1;
  for (let i = start; i < cssContent.length; i++) {
    const ch = cssContent[i];
    if (ch === '{')      depth++;
    else if (ch === '}') { depth--; if (depth === 0) { end = i; break; } }
  }
  if (end === -1) return null;
  return cssContent.slice(start, end).trim();
}

function switchToCodeMode(xhtml = '') {
  if (!currentChapterFile) return Promise.resolve();
  return new Promise((resolve) => {
  // Use provided xhtml, or get from Monaco if already loaded, or empty string
  const content = xhtml || (editorMode === 'code' && monacoEditor ? monacoEditor.getValue() : '');
  editorMode = 'code';
  // ... rest of function, but use `content` instead of `xhtml`
  document.getElementById('editor-scroll').classList.remove('active');
  document.getElementById('monaco-container').classList.add('active');

  // DISABLED: No toggle button
  // document.getElementById('btn-toggle-mode').textContent = '¶ Text';
  // document.getElementById('btn-toggle-mode').classList.add('active-toggle');

  document.getElementById('editor-mode-badge').textContent = 'CODE';
  document.getElementById('monaco-fs-control').style.display = 'flex';
  // DISABLED: lt-only controls not needed - grammar button is now always visible
  // document.querySelectorAll('.lt-only').forEach(el => el.style.display = 'none');
  hideLtPopover();
  initMonaco(err => {
    if (err) { 
      setEditorStatus('Monaco not available — check installation', 'err');
      // DISABLED: No text mode fallback
      // switchToTextMode();
      return;
    }

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

        // CSS
        { token: 'tag.css',             foreground: '007020', fontWeight: 'bold' },
        { token: 'attribute.name.css',  foreground: '7b5694' },
        { token: 'attribute.value.css', foreground: '4070a0' },
        { token: 'delimiter.css',       foreground: '808080' },
        { token: 'delimiter.bracket.css', foreground: '808080' },
        { token: 'string.css',          foreground: '4070a0' },
        { token: 'comment.css',         foreground: 'a0b0c0', fontStyle: 'italic' },
        { token: 'keyword.css',         foreground: 'a07040' },

      ],
      colors: {
        'editor.background': '#f0f0f0',           // pyte-light BG
        'editor.foreground': '#404850',           // pyte-light FG
        'editorLineNumber.background': '#8090a0', // LineNr BG
        'editorLineNumber.foreground': '#8090a0', // LineNr FG (white)
        'editor.lineHighlightBackground': '#F8DE7E55', // cursor_loc with transparency
      }
    });
    
    // XHTML configuration
    monaco.languages.html.htmlDefaults.setOptions({
      suggest: { html5: false }
    });

    const container = document.getElementById('monaco-container');
    if (!monacoEditor) {
      monacoLoading = true;
      monacoEditor = monaco.editor.create(container, {
        value: content, // CHANGED: Use content parameter, not xhtml
        language: 'xml', 
        theme: 'pyteLight', 
        snippetSuggestions: 'none',
        fontSize: parseInt(localStorage.getItem(MONACO_FS_KEY)) || MONACO_FS_DEFAULT,
        fontFamily: "'IBM Plex Mono', monospace", 
        lineNumbers: 'on',
        wordWrap: 'on', 
        minimap: { enabled: false },
        scrollBeyondLastLine: false, 
        automaticLayout: true,
        autoClosingTags: false, 
        formatOnType: false, 
        formatOnPaste: false,
      });
      monacoLoading = false;
      // monacoEditor.onDidChangeModelContent(() => {
      //   if (!monacoLoading) {
      //     isDirty = true;
      //     debouncedRefreshPreview();
      //   }
      // });

      monacoEditor.onDidChangeModelContent(() => {
        if (!monacoLoading) {
          isDirty = true;
          
          if (currentChapterFile.endsWith('.css')) {
            // If editing CSS, only refresh the styles (keeps the current HTML)
            debouncedStyleRefresh(); 
          } else {
            // If editing XHTML, refresh everything
            debouncedRefreshPreview();
          }
        }
      });

    } else {
      // Editor already exists, just update content
      monacoLoading = true;
      monacoEditor.setValue(content); // Use content parameter
      monacoLoading = false;
      setTimeout(() => { isDirty = false; }, 0);
    }
    resolve();
  }); // initMonaco
  }); // Promise
}

// ── Editor: save ─────────────────────────────────────────────────────────────

function onEditorKeydown(e) {
  if ((e.ctrlKey||e.metaKey) && e.key==='s') { e.preventDefault(); saveChapter(); }
}

function formatXhtml() {
  if (!monacoEditor) return;
  const raw = monacoEditor.getValue();
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(raw, 'application/xml');
    const err = doc.querySelector('parsererror');
    if (err) {
      setEditorStatus('✗ Cannot format — XML is not valid', 'err');
      return;
    }
    const pretty = _prettyPrintXml(doc.documentElement, 0);
    const decl   = raw.match(/^<\?xml[^?]*\?>\s*/)?.[0] || "<?xml version='1.0' encoding='utf-8'?>\n";
    monacoEditor.setValue(decl + pretty);
    setEditorStatus('✓ Formatted', 'ok');
  } catch(e) {
    setEditorStatus('✗ Format failed: ' + e.message, 'err');
  }
}

function _prettyPrintXml(node, depth) {
  const indent = '  '.repeat(depth);
  // Modern equivalents strong and em added
  const INLINE = new Set(['b', 'i', 'em', 'strong', 'span', 'a', 'sup', 'sub', 'abbr', 'cite', 'code', 'q', 'small', 'br']);
  const VOID_TAGS = new Set(['br', 'link', 'meta', 'img', 'hr']);

  if (node.nodeType === Node.TEXT_NODE) {
    // Collapse whitespace but keep original string if depth is 0 (inline)
    const text = node.textContent.replace(/\s+/g, ' ');
    if (depth > 0) {
      const trimmed = text.trim();
      return trimmed ? indent + trimmed : '';
    }
    return text;
  }

  if (node.nodeType === Node.COMMENT_NODE) {
    return `${indent}`;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) return '';

  const tag = node.tagName.toLowerCase();
  const attrs = Array.from(node.attributes)
    .map(a => `${a.name}="${a.value.replace(/"/g, '&quot;')}"`)
    .join(' ');
  
  const openTag = attrs ? `<${tag} ${attrs}>` : `<${tag}>`;
  const closeTag = `</${tag}>`;

  if (VOID_TAGS.has(tag)) {
    return `${indent}<${tag}${attrs ? ' ' + attrs : ''} />`;
  }

  const children = Array.from(node.childNodes);

  if (INLINE.has(tag) || tag === 'p') {
    const inner = children.map(c => {
      const cTag = c.tagName?.toLowerCase();
      if (c.nodeType === Node.TEXT_NODE) {
        // Preserves the single space needed for "un <i>child</i>"
        return c.textContent.replace(/\s+/g, ' ');
      }
      if (cTag === 'br') {
        return `<br />\n${indent}`; 
      }
      return _prettyPrintXml(c, 0); 
    }).join('');

    // Only trim the very outer edges of the paragraph/inline block
    const result = `${indent}${openTag}${inner.trim()}${closeTag}`;
    return tag === 'p' ? result + '\n' : result;
  }

  const childLines = children
    .map(c => _prettyPrintXml(c, depth + 1))
    .filter(s => s.trim() !== '');

  if (childLines.length === 0) {
    return `${indent}${openTag}${closeTag}`;
  }

  return `${indent}${openTag}\n${childLines.join('\n')}\n${indent}${closeTag}`;
}

// function _prettyPrintXml(node, depth) {
//   const indent = '  '.repeat(depth);
//   if (node.nodeType === Node.TEXT_NODE) {
//     const t = node.textContent;
//     // Preserve soft hyphens and non-breaking spaces, trim only leading/trailing newlines
//     const trimmed = t.replace(/^\n+|\n+$/g, '');
//     return trimmed ? indent + trimmed : '';
//   }
//   if (node.nodeType === Node.COMMENT_NODE) {
//     return `${indent}<!--${node.nodeValue}-->`;
//   }
//   if (node.nodeType !== Node.ELEMENT_NODE) return '';

//   const tag   = node.tagName;
//   const attrs = Array.from(node.attributes)
//     .map(a => `${a.name}="${a.value.replace(/"/g, '&quot;')}"`)
//     .join(' ');
//   const open  = attrs ? `<${tag} ${attrs}>` : `<${tag}>`;

//   const children = Array.from(node.childNodes);

//   // Inline elements — keep on one line
//   const INLINE = new Set(['b','i','em','strong','span','a','sup','sub','abbr','cite','code','q','small']);
//   const hasOnlyInline = children.every(c =>
//     c.nodeType === Node.TEXT_NODE ||
//     (c.nodeType === Node.ELEMENT_NODE && INLINE.has(c.tagName.toLowerCase()))
//   );

//   if (children.length === 0) {
//     return `${indent}<${tag}${attrs ? ' ' + attrs : ''}/>`;
//   }

//   if (hasOnlyInline || INLINE.has(tag.toLowerCase())) {
//     // Serialize inline content as-is
//     const inner = children.map(c => {
//       if (c.nodeType === Node.TEXT_NODE) return c.textContent;
//       if (c.nodeType === Node.COMMENT_NODE) return `<!--${c.nodeValue}-->`;
//       const ca = Array.from(c.attributes).map(a => `${a.name}="${a.value.replace(/"/g, '&quot;')}"`).join(' ');
//       const co = Array.from(c.childNodes).map(cc => cc.textContent).join('');
//       return ca ? `<${c.tagName} ${ca}>${co}</${c.tagName}>` : `<${c.tagName}>${co}</${c.tagName}>`;
//     }).join('');
//     return `${indent}${open}${inner}</${tag}>`;
//   }

//   const childLines = children
//     .map(c => _prettyPrintXml(c, depth + 1))
//     .filter(s => s !== '');

//   return `${indent}${open}\n${childLines.join('\n')}\n${indent}</${tag}>`;
// }

async function saveChapter() {
  if (!currentChapterFile) return;
  // CHANGED: Get XHTML from Monaco (code mode only)
  // const xhtml = serializeToXhtml();
  const xhtml = monacoEditor ? monacoEditor.getValue() : '';
  if (!xhtml) { setEditorStatus('No content to save', 'err'); return; }

  // Visual feedback — invert Save button colours for 500ms
  const saveBtn = document.getElementById('btn-save-chapter');
  if (saveBtn) {
    saveBtn.classList.add('btn-saving');
    setTimeout(() => saveBtn.classList.remove('btn-saving'), 500);
  }
  
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
    if (previewVisible) debouncedRefreshPreview();

    // Resync CSS tokens when a CSS file is saved — new tokens may have been added
    if (isCss) {
      apiFetch('POST', `/projects/${currentProject.id}/css-tokens/sync`).catch(() => {});
      if (typeof invalidateCssTokensCache === 'function') invalidateCssTokensCache();
    }

    // If this is a front/back matter file (not a chapter), refresh its Build preview
    if (!isChapter && !isCss && currentChapterFile) {
      const item = { filename: currentChapterFile };
      await previewBuildItem(item);
    }
  } catch(e) { setEditorStatus('Save failed: ' + e.message, 'err'); }
}

function onEditorContentInput() {
  isDirty = true;
  if (ltMatches.length) { ltMatches = []; setEditorStatus('Text edited — recheck to refresh marks', 'warn'); }
  debouncedRefreshPreview();
}
// ── Preview → Code sync ───────────────────────────────────────────────────────
// Click a block element in the preview → jump to that text in Monaco

function onPreviewClick(e) {
  // Skip if clicking a grammar mark (handled separately)
  if (e.target.closest('.lt-err')) return;
  if (!monacoEditor) return;

  // Walk up to nearest meaningful block element
  const BLOCK_TAGS = new Set(['p','h1','h2','h3','h4','h5','h6','li','blockquote','div','td','th']);
  let el = e.target;
  while (el && el !== e.currentTarget) {
    if (BLOCK_TAGS.has(el.tagName.toLowerCase())) break;
    el = el.parentElement;
  }
  if (!el || el === e.currentTarget) return;

  // Extract needle as text up to the first <br/> — handles plain text, <i>text</i>,
  // mixed inline content, and any combination. textContent is NOT used because it
  // concatenates <br/>-separated lines into a string that doesn't exist in the source.
  let needle = '';
  const INLINE_TAGS = new Set(['i','em','b','strong','span','a','sup','sub']);
  let collected = '';
  for (const node of el.childNodes) {
    if (node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() === 'br') break;
    if (node.nodeType === Node.TEXT_NODE) {
      collected += node.textContent;
    } else if (node.nodeType === Node.ELEMENT_NODE && INLINE_TAGS.has(node.tagName.toLowerCase())) {
      collected += node.textContent;
    }
    if (collected.replace(/\s+/g, ' ').trim().length >= 60) break;
  }
  needle = collected.replace(/\s+/g, ' ').trim().slice(0, 60);
  // Fall back to full textContent for elements without <br/> structure
  if (needle.length < 3) {
    const rawText = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!rawText || rawText.length < 3) return;
    needle = rawText.slice(0, 60);
  }

  const model = monacoEditor.getModel();
  if (!model) return;

  // Search in Monaco source — escape special regex chars
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const matches = model.findMatches(escaped, false, true, false, null, false);
  if (!matches || !matches.length) return;

  const line = matches[0].range.startLineNumber;
  monacoEditor.revealLineInCenter(line);
  monacoEditor.setPosition({ lineNumber: line, column: 1 });
  monacoEditor.focus();
}

const debouncedStyleRefresh = debounce(async () => { 
  if (previewVisible && currentChapterFile.endsWith('.css')) {
    // Clear the cache for the file we are currently editing so it pulls fresh Monaco content
    delete cachedStyles[currentChapterFile]; 
    await loadPreviewStyles(); 
  }
}, 300);