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
        el.textContent = ch.filename;
        // el.textContent = ch.name || ch.filename;
        el.title = ch.filename;
        el.onclick = () => openChapter(ch.filename, el);
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
      
      // DISABLED: Don't duplicate - switchToCodeMode already loads content
      // if (monacoEditor) {
      //   const model = monacoEditor.getModel();
      //   if (model) monaco.editor.setModelLanguage(model, 'xml');
      //   monacoLoading = true;
      //   monacoEditor.setValue(data.content);
      //   monacoLoading = false;
      //   setTimeout(() => { isDirty = false; }, 0);
      // }
      
      // DISABLED: Text mode removed - no need to update text editor
      // document.getElementById('editor-content').innerHTML = bodyHtmlLoad;
      // document.getElementById('editor-content').dataset.rawXhtml = data.content;
      
      setEditorStatus('', '');
      
      // CHANGED (STEP 11): Ensure preview always visible
      if (!previewVisible) {
        previewVisible = true;
        document.querySelector('.editor-layout').classList.add('preview-open');
        document.getElementById('preview-pane').classList.add('active');
      }
      await loadPreviewStyles();
      await refreshPreview();
    }
  } catch(e) { setEditorStatus('Error loading file', 'err'); }
}

// ── Preview pane ──────────────────────────────────────────────────────────────
let previewMode = 'digital';  // 'digital' or 'print'

function togglePreviewMode() {
  previewMode = previewMode === 'digital' ? 'print' : 'digital';
  const btn = document.getElementById('btn-preview-mode-toggle');
  btn.classList.toggle('mode-digital');
  btn.classList.toggle('mode-print');
  
  if (previewVisible) {
    cachedStyles = {};
    loadPreviewStyles();
    refreshPreview();
  }
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
let _tokensJsonCache = null;
let _fnMapCache      = null;
let _fnMapProjectId  = null;

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

  // Enrich fn-marker spans with footnote content as tooltip
  const fnSpans = pane.querySelectorAll('.fn-marker');
  if (fnSpans.length) {
    const fnMap = await _getFnMap();
    fnSpans.forEach(span => {
      const id = span.getAttribute('data-fn');
      if (id && fnMap[id]) span.title = `[${span.getAttribute('data-display')}] ${fnMap[id]}`;
    });
  }

  if (ltMatches && ltMatches.length) applyLtMarks(ltMatches);
}

async function loadPreviewStyles() {
  const pane = document.getElementById('preview-pane-body');
  const oldStyles = pane.parentNode.querySelectorAll('style');
  oldStyles.forEach(s => s.remove());

  let linkEls = [];
  
  // IF EDITING XHTML: Extract and save the stylesheet list
  if (!currentChapterFile.endsWith('.css')) {
    let xhtml = monacoEditor ? monacoEditor.getValue() : '';
    const parser = new DOMParser();
    const doc = parser.parseFromString(xhtml, 'text/html');
    linkEls = Array.from(doc.querySelectorAll('link[rel="stylesheet"]'));
    
    // Update our "memory" of what stylesheets this XHTML uses
    lastXhtmlStylesheets = linkEls.map(link => link.getAttribute('href'));
  } 
  
  // Use either the current links OR the "remembered" links if editing CSS
  const stylesheetHrefs = currentChapterFile.endsWith('.css') 
    ? lastXhtmlStylesheets 
    : linkEls.map(link => link.getAttribute('href'));

  for (const href of stylesheetHrefs) {
    const cssFilename = href.split('/').pop();
    
    // IMPORTANT: If we are CURRENTLY editing this specific CSS file, 
    // use the content from Monaco instead of the saved version.
    if (currentChapterFile === cssFilename && monacoEditor) {
      const styleEl = document.createElement('style');
      styleEl.textContent = monacoEditor.getValue();
      pane.parentNode.insertBefore(styleEl, pane);
      continue;
    }

    // Otherwise, use cache or fetch from server as before
    if (cachedStyles[cssFilename]) {
      const styleEl = document.createElement('style');
      styleEl.textContent = cachedStyles[cssFilename];
      pane.parentNode.insertBefore(styleEl, pane);
    } else {
      try {
        const cssData = await apiFetch('GET', `/projects/${currentProject.id}/styles/${cssFilename}`);
        cachedStyles[cssFilename] = cssData.content || '';
        const styleEl = document.createElement('style');
        styleEl.textContent = cachedStyles[cssFilename];
        pane.parentNode.insertBefore(styleEl, pane);
      } catch(e) { console.warn(`CSS fetch failed: ${cssFilename}`); }
    }
  }

  // Load overrides (keep your existing logic for print/digital overrides here)
  // ...

  // Load overrides
// Load overrides
  const overrideFilename = previewMode === 'print' ? 'print-overrides.css' : 'digital-overrides.css';
  try {
    let overrideContent = '';

    // NEW: Check if we are currently editing the override file itself
    if (currentChapterFile === overrideFilename && monacoEditor) {
      overrideContent = monacoEditor.getValue();
    } else if (cachedStyles[overrideFilename]) {
      // Already extracted and cached — insert directly, no need to re-extract
      const styleEl = document.createElement('style');
      styleEl.textContent = cachedStyles[overrideFilename];
      pane.parentNode.insertBefore(styleEl, pane);
      overrideContent = ''; // nothing left to extract
    } else {
      const overrideData = await apiFetch('GET', `/projects/${currentProject.id}/styles/${overrideFilename}`);
      overrideContent = overrideData.content || '';
    }

    // Extract rules from the editor content or fetched content (skipped if overrideContent is empty)
    if (overrideContent) {
      const extractedRules = extractMediaRules(overrideContent, previewMode === 'print' ? '@media print' : '@media screen');
      if (extractedRules) {
        // Only cache if we aren't currently live-editing it
        if (currentChapterFile !== overrideFilename) {
          cachedStyles[overrideFilename] = extractedRules;
        }
        const styleEl = document.createElement('style');
        styleEl.textContent = extractedRules;
        pane.parentNode.insertBefore(styleEl, pane);
      }
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