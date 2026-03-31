'use strict';

let _draggedMarker = null; // currently dragged split marker object

async function checkExistingChapters() {
  try {
    const existingChapters = await apiFetch('GET', `/projects/${currentProject.id}/chapters`);
    const banner = document.getElementById('split-existing-banner');
    if (existingChapters.length) {
      banner.style.display = '';
      banner.innerHTML = `<span>⚠ ${existingChapters.length} chapter file${existingChapters.length !== 1 ? 's' : ''} already exist — applying new splits will replace them.</span>`;
    } else {
      banner.style.display = 'none';
      banner.innerHTML = '';
    }
  } catch(e) { /* ignore */ }
}

// ── Split panel ──────────────────────────────────────────────────────────────
async function loadFullXhtml() {
  const area = document.getElementById('split-text-area');
  area.innerHTML = '<div style="font-family:var(--mono);font-size:0.78rem;color:var(--text3);padding:2rem 0">Loading manuscript…</div>';
  splitElements = []; splitMarkers = [];
  updateSplitList();
  showStatus('split-status', '', '');

  await checkExistingChapters();

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
      wrapper.addEventListener('click', (e) => {
        const area = document.getElementById('split-text-area');
        if (area.classList.contains('footnotes-mode') && (fnPickActive || fnMoveActive)) {
          console.log('[fn] text click in pick/move mode, xhtmlIndex:', i);
          onFootnotePickClick(e, i, wrapper);
        } else if (!area.classList.contains('footnotes-mode')) {
          addSplitMarker(i, wrapper);
        }
      });
      wrapper.addEventListener('dragover', e => {
        if (!_draggedMarker) return;
        e.preventDefault();
        wrapper.classList.add('drag-over');
      });
      wrapper.addEventListener('dragleave', () => wrapper.classList.remove('drag-over'));
      wrapper.addEventListener('drop', e => {
        e.preventDefault();
        wrapper.classList.remove('drag-over');
        if (!_draggedMarker) return;
        const newIndex = i;
        // Don't drop on same position or where another marker already exists
        if (_draggedMarker.beforeIndex === newIndex) return;
        if (splitMarkers.find(m => m !== _draggedMarker && m.beforeIndex === newIndex)) return;
        // Move marker DOM before this wrapper
        wrapper.parentNode.insertBefore(_draggedMarker.marker, wrapper);
        _draggedMarker.beforeIndex = newIndex;
        syncSavedData();
      });
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

    // If no editable markers and chapters on disk have before_index, insert readonly markers
    if (!splitMarkers.length) {
      const chapters = currentProject?.chapters || [];
      const hasPositions = chapters.some(c => c.before_index !== undefined);
      if (hasPositions) {
        chapters.forEach(ch => {
          if (ch.before_index === undefined) return;
          const el = splitElements[ch.before_index];
          if (el) _insertMarkerDOM(ch.before_index, el, ch.type, ch.name, true);
        });
      }
    }

    // Auto-populate class input from first h1 found (wrapper class takes priority)
    try {
      const classInput = document.getElementById('auto-classes');
      if (classInput && !classInput.value.trim()) {
        let detected = '';
        for (const wrapper of splitElements) {
          const h1 = wrapper.querySelector('h1');
          if (!h1) continue;
          const parent = h1.parentElement;
          if (parent && parent !== wrapper && parent.className) {
            detected = parent.className;
          } else if (h1.className) {
            detected = h1.className;
          }
          break;
        }
        if (detected) classInput.value = detected;
      }
    } catch(e) { /* best effort */ }
  } catch(e) {
    area.innerHTML = `<p style="color:var(--accent)">Error: ${e.message}</p>`;
  }
}

function _insertMarkerDOM(beforeIndex, wrapperEl, type, name, readOnly = false) {
  const marker = document.createElement('div');
  marker.className = 'split-marker';
  marker.draggable = true;
  marker.innerHTML = `
    <div class="split-marker-line"></div>
    <select class="marker-type">
      <option value="chapter">Chapter</option>
      <option value="part">Part</option>
      <option value="subchapter">Subchapter</option>
      <option value="record">Record</option>
      <option value="front_matter">Front matter</option>
      <option value="back_matter">Back matter</option>
    </select>
    <input class="marker-name" type="text" placeholder="Name / title…">
    <button class="split-marker-del" title="Remove">×</button>
    <span class="split-marker-handle" title="Drag to move">⠿</span>
  `;
  wrapperEl.parentNode.insertBefore(marker, wrapperEl);
  marker.querySelector('.marker-type').value = type || 'chapter';
  marker.querySelector('.marker-name').value = name || '';
  const obj = { beforeIndex, marker, readOnly };
  splitMarkers.push(obj);

  if (readOnly) {
    marker.classList.add('split-marker--readonly');
    marker.draggable = false;
  } else {
    marker.addEventListener('dragstart', e => { _draggedMarker = obj; e.dataTransfer.effectAllowed = 'move'; setTimeout(() => marker.style.opacity = '0.4', 0); });
    marker.addEventListener('dragend',   () => { marker.style.opacity = ''; _draggedMarker = null; });
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
  }
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
  const list      = document.getElementById('split-list');
  const head      = document.getElementById('split-list-head');
  const countEl   = document.getElementById('split-count');
  const applyBtn  = document.getElementById('btn-apply-splits');
  const clearBtn  = document.getElementById('btn-clear-splits');
  const deleteBtn = document.getElementById('btn-delete-chapters');

  const hasReadOnly  = splitMarkers.some(m => m.readOnly);
  const hasEditable  = splitMarkers.some(m => !m.readOnly);
  const chaptersMode = hasReadOnly && !hasEditable;

  countEl.textContent = splitMarkers.length;

  // Update header label
  if (head) head.innerHTML = chaptersMode
    ? `Chapters on disk — <span id="split-count">${splitMarkers.length}</span>`
    : `Split points — <span id="split-count">${splitMarkers.length}</span>`;

  // Show/hide buttons based on state
  if (applyBtn)  applyBtn.classList.toggle('hidden', chaptersMode);
  if (clearBtn)  clearBtn.classList.toggle('hidden', chaptersMode);
  if (deleteBtn) deleteBtn.classList.toggle('hidden', !chaptersMode);

  if (!splitMarkers.length) {
    list.innerHTML = '<div class="split-list-empty">No splits yet.<br>Click in the text to add one.</div>';
    return;
  }
  const sorted = [...splitMarkers].sort((a,b) => a.beforeIndex - b.beforeIndex);
  list.innerHTML = '';
  sorted.forEach(m => {
    const type = m.marker.querySelector('.marker-type').value;
    const name = m.marker.querySelector('.marker-name').value || '(unnamed)';
    const el   = document.createElement('div');
    el.className = 'split-list-item';
    el.style.cursor = 'pointer';
    if (m.readOnly) {
      el.innerHTML = `<span class="sli-applied">✓ ${type}</span>${escHtml(name)}`;
    } else {
      el.innerHTML = `<span class="sli-type">${type}</span>${escHtml(name)}`;
    }
    el.addEventListener('click', () => m.marker.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    list.appendChild(el);
  });
}

function autoSplitDetect() {
  if (!splitElements.length) {
    showStatus('split-status', 'Load the manuscript first', 'err');
    return;
  }

  const tags = [];
  if (document.getElementById('auto-h1').checked) tags.push('h1');
  if (document.getElementById('auto-h2').checked) tags.push('h2');
  if (document.getElementById('auto-h3').checked) tags.push('h3');

  const classInput = document.getElementById('auto-classes').value.trim();
  const classes = classInput ? classInput.split(',').map(c => c.trim()).filter(Boolean) : [];

  if (!tags.length && !classes.length) {
    showStatus('split-status', 'Select at least one heading or enter a CSS class', 'err');
    return;
  }

  let added = 0;
  splitElements.forEach((wrapper, idx) => {
    // Check the direct child AND any descendant (handles wrapped headings)
    const directEl = wrapper.firstElementChild;
    if (!directEl) return;
    const directTag = directEl.tagName.toLowerCase();

    // For tag matching: check direct child tag, or if direct child wraps the tag
    const matchesTag = tags.some(t => {
      if (directTag === t) return true;
      return !!wrapper.querySelector(t);
    });

    // For class matching: check direct child classes and all descendant classes
    const allEls = [directEl, ...directEl.querySelectorAll('*')];
    const matchesClass = classes.some(c => allEls.some(el => el.classList.contains(c)));

    if (matchesTag || matchesClass) {
      if (!splitMarkers.find(m => m.beforeIndex === idx)) {
        _insertMarkerDOM(idx, wrapper, 'chapter', '');
        added++;
      }
    }
  });

  syncSavedData();
  showStatus('split-status', added ? `⚡ ${added} split${added !== 1 ? 's' : ''} added` : 'No new matches found', added ? 'ok' : 'warn');
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
    // Single endpoint: deletes all chapter files, clears build_config.json chapters,
    // and resets meta.json status → 'converted'. Replaces the old per-file DELETE loop
    // which left meta.json and build_config.json in a stale 'split' state.
    const result = await apiFetch('POST', `/projects/${currentProject.id}/chapters/delete-all`);

    if (result.errors && result.errors.length) {
      showStatus('split-status', `⚠ ${result.errors.length} file${result.errors.length !== 1 ? 's' : ''} could not be deleted`, 'err');
    } else {
      showStatus('split-status', `✓ ${result.deleted.length} chapter file${result.deleted.length !== 1 ? 's' : ''} deleted`, 'ok');
    }

    banner.style.display = 'none';
    banner.innerHTML = '';

    // Sync in-memory project state — backend has already written these to disk
    currentProject.chapters = [];
    currentProject.status   = 'converted';
    _updateFootnotesTabState(); // immediately remove strikethrough from Footnotes labels

    // Clear split UI state
    localStorage.removeItem('splits:' + currentProject.id);
    buildConfig = null; // force Build panel to reload
    loadBuildConfig();
    splitMarkers.forEach(m => m.marker.remove());
    splitMarkers   = [];
    splitSavedData = [];
    updateSplitList();
  } catch(e) { showStatus('split-status', '✗ ' + e.message, 'err'); }
}

async function applySplits() {
  if (!splitMarkers.length) { showStatus('split-status', 'Add at least one split point first', 'err'); return; }
  // Warn if chapters exist on disk and user hasn't already seen readonly markers
  const existingCount = (currentProject?.chapters || []).length;
  const alreadyShowingReadonly = splitMarkers.some(m => m.readOnly);
  if (existingCount && !alreadyShowingReadonly) {
    const ok = confirm(`${existingCount} chapter file${existingCount !== 1 ? 's' : ''} already exist and will be replaced.\n\nContinue?`);
    if (!ok) return;
  }
  const sorted = [...splitMarkers].sort((a,b) => a.beforeIndex - b.beforeIndex);
  const splits = sorted.map((m, i) => {
    const type = m.marker.querySelector('.marker-type').value;
    const name = m.marker.querySelector('.marker-name').value.trim() || `${i+1}`;

    // console.log('Split marker:', { index: i, type, name, beforeIndex: m.beforeIndex });

    return { before_index: m.beforeIndex, type, name };
  });
  const btn = document.getElementById('btn-apply-splits');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Splitting…';
  showStatus('split-status', 'Generating chapter files…', 'info');
  try {
    const data = await apiFetch('POST', `/projects/${currentProject.id}/split`, { splits });
    showStatus('split-status', `\u2713 ${data.saved.length} files created`, 'ok');
    currentProject.status = 'split'; currentProject.chapters = data.saved;
    _updateFootnotesTabState(); // immediately apply strikethrough to Footnotes labels
    buildConfig = null; // force Build panel to reload
    // Replace editable markers with readonly ones from saved chapters
    splitMarkers.forEach(m => m.marker.remove());
    splitMarkers = []; splitSavedData = [];
    if (currentProject) localStorage.removeItem('splits:' + currentProject.id);
    data.saved.filter(c => c.before_index !== undefined).forEach(ch => {
      const el = splitElements[ch.before_index];
      if (el) _insertMarkerDOM(ch.before_index, el, ch.type, ch.name, true);
    });
    await checkExistingChapters();
  } catch(e) { showStatus('split-status', '✗ ' + e.message, 'err'); }
  finally { btn.disabled = false; btn.textContent = '✂ Apply splits'; }
}