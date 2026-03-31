'use strict';

const FN_CONTEXT_CHARS = 50;
let fnPickActive      = false;
let fnPickInsertAfter = null; // display_num after which to insert
let fnPickZoneEl      = null; // the active .fn-add-zone element
let fnPickData        = null; // { xhtmlIndex, charOffset }

let fnMoveActive     = false;
let fnMoveDisplayNum = null;
let fnMoveBtn        = null;

function deactivateMoveMode() {
  if (fnMoveBtn) fnMoveBtn.classList.remove('move-active');
  fnMoveActive     = false;
  fnMoveDisplayNum = null;
  fnMoveBtn        = null;
}

// ── Split / Footnotes sidebar toggle ─────────────────────────────────────────
function showSplitsView() {
  document.getElementById('split-view').style.display    = 'flex';
  document.getElementById('footnotes-view').style.display = 'none';
  document.getElementById('btn-split-tab-splits').classList.add('active');
  document.getElementById('btn-split-tab-footnotes').classList.remove('active');
  document.getElementById('split-text-area').classList.remove('footnotes-mode');
  deactivatePickMode();
}

function showFootnotesView() {
  document.getElementById('split-view').style.display    = 'none';
  document.getElementById('footnotes-view').style.display = 'flex';
  document.getElementById('btn-split-tab-splits').classList.remove('active');
  document.getElementById('btn-split-tab-footnotes').classList.add('active');
  document.getElementById('split-text-area').classList.add('footnotes-mode');
  loadFootnotesReview();
}

// ── Footnote pick mode ────────────────────────────────────────────────────────
function activatePickMode(zoneEl, insertAfterNum) {
  deactivatePickMode(); // close any existing
  fnPickActive      = true;
  fnPickInsertAfter = insertAfterNum;
  fnPickZoneEl      = zoneEl;
  fnPickData        = null;
  zoneEl.classList.add('pick-active');
  // Hide form until position is picked
  const form = zoneEl.nextElementSibling;
  if (form && form.classList.contains('fn-add-form')) {
    form.classList.remove('visible');
  }
}

function deactivatePickMode() {
  if (fnPickZoneEl) fnPickZoneEl.classList.remove('pick-active');
  fnPickActive      = false;
  fnPickInsertAfter = null;
  fnPickZoneEl      = null;
  fnPickData        = null;
  deactivateMoveMode();
}

function onFootnotePickClick(e, xhtmlIndex, wrapper) {
  // Move mode takes priority over pick/add mode
  if (fnMoveActive) {
    const fullText = wrapper.innerText || wrapper.textContent;
    let charOffset = 0;
    let node, offset;
    if (document.caretRangeFromPoint) {
      const range = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (!range) return;
      node = range.startContainer; offset = range.startOffset;
    } else if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY);
      if (!pos) return;
      node = pos.offsetNode; offset = pos.offset;
    } else { return; }
    const walker = document.createTreeWalker(wrapper, NodeFilter.SHOW_TEXT);
    let current;
    while ((current = walker.nextNode())) {
      if (current === node) { charOffset += offset; break; }
      charOffset += current.textContent.length;
    }
    moveFootnote(xhtmlIndex, charOffset);
    return;
  }

  if (!fnPickZoneEl) return;
    let node, offset;
    if (document.caretRangeFromPoint) {
      const range = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (!range) return;
      node   = range.startContainer;
      offset = range.startOffset;
    } else if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY);
      if (!pos) return;
      node   = pos.offsetNode;
      offset = pos.offset;
    } else {
      return;
    }

  // Collect plain text of wrapper, tracking char offset
  const fullText  = wrapper.innerText || wrapper.textContent;

  // Find offset within full wrapper text by walking to the clicked node
  let charOffset = 0;
  const walker = document.createTreeWalker(wrapper, NodeFilter.SHOW_TEXT);
  let current;
  while ((current = walker.nextNode())) {
    if (current === node) { charOffset += offset; break; }
    charOffset += current.textContent.length;
  }

  const before  = fullText.slice(Math.max(0, charOffset - FN_CONTEXT_CHARS), charOffset);
  const after   = fullText.slice(charOffset, charOffset + FN_CONTEXT_CHARS);

  fnPickData = { xhtmlIndex, charOffset };

  // Populate context and show form
  const form = fnPickZoneEl.nextElementSibling;
  if (form && form.classList.contains('fn-add-form')) {
    const ctxEl = form.querySelector('.fn-context-display');
    const taEl  = form.querySelector('.fn-add-textarea');
    const ctrlEl = form.querySelector('.fn-add-controls');
    ctxEl.innerHTML = `…${before}<span class="fn-context-cursor">▌</span>${after}…`;
    ctxEl.style.display  = 'block';
    taEl.value           = '';
    taEl.style.display   = 'block';
    ctrlEl.style.display = 'flex';
    form.classList.add('visible');
    taEl.focus();
  }
  fnPickZoneEl.classList.remove('pick-active');
  fnPickActive = false;
}

async function saveNewFootnote(zoneEl, insertAfterNum) {
  if (!fnPickData) { alert('Click in the text to set the footnote position first.'); return; }
  const form    = zoneEl.nextElementSibling;
  const content = form.querySelector('.fn-add-textarea').value.trim();
  if (!content) { alert('Please enter footnote content.'); return; }

  try {
    await apiFetch('POST', `/projects/${currentProject.id}/footnotes/add`, {
      xhtml_index:      fnPickData.xhtmlIndex,
      char_offset:      fnPickData.charOffset,
      content,
      insert_after_num: insertAfterNum,
    });
    deactivatePickMode();
    await loadFullXhtml();
    await loadFootnotesReview();
    // Scroll to newly created marker — it will be at insertAfterNum + 1
    const newNum = insertAfterNum + 1;
    const allSpans = document.querySelectorAll('#split-text-area .fn-marker');
    for (const span of allSpans) {
      if (span.getAttribute('data-display') === String(newNum)) {
        span.scrollIntoView({ behavior: 'smooth', block: 'center' });
        span.classList.add('fn-marker-highlight');
        setTimeout(() => span.classList.remove('fn-marker-highlight'), 1500);
        break;
      }
    }
  } catch(e) {
    alert('Failed to add footnote: ' + e.message);
  }
}

async function moveFootnote(xhtmlIndex, charOffset) {
  const displayNum = fnMoveDisplayNum;
  deactivateMoveMode();
  try {
    await apiFetch('PATCH', `/projects/${currentProject.id}/footnotes/${displayNum}/position`, {
      xhtml_index: xhtmlIndex,
      char_offset: charOffset,
    });
    await loadFullXhtml();
    await loadFootnotesReview();
    // Scroll to moved marker
    const allSpans = document.querySelectorAll('#split-text-area .fn-marker');
    for (const span of allSpans) {
      if (span.getAttribute('data-display') === String(displayNum)) {
        span.scrollIntoView({ behavior: 'smooth', block: 'center' });
        span.classList.add('fn-marker-highlight');
        setTimeout(() => span.classList.remove('fn-marker-highlight'), 1500);
        break;
      }
    }
  } catch(e) {
    alert('Failed to move footnote: ' + e.message);
  }
}

// ── Footnotes tab state ───────────────────────────────────────────────────────
// Called immediately when project status changes (split ↔ converted) so the
// Footnotes tab label and header span update without waiting for tab navigation.
function _updateFootnotesTabState() {
  const chaptersExist = currentProject?.status === 'split';
  const tabBtn     = document.getElementById('btn-split-tab-footnotes');
  const headerSpan = document.querySelector('#footnotes-view .split-sidebar-head span');
  [tabBtn, headerSpan].forEach(el => {
    if (!el) return;
    el.style.textDecoration = chaptersExist ? 'line-through' : '';
    el.style.opacity        = chaptersExist ? '0.45'         : '';
  });
}

async function loadFootnotesReview() {
  const list = document.getElementById('footnotes-review-list');
  list.innerHTML = '<div class="split-list-empty">Loading…</div>';

  const issuesBtn = document.getElementById('btn-fn-issues');
  issuesBtn.style.display = 'none';
  let issuesFilterActive = issuesBtn._filterActive || false;

  if (!currentProject) {
    list.innerHTML = '<div class="split-list-empty">No project open.</div>';
    return;
  }

  // #17: Read-only mode driven by project status. _updateFootnotesTabState()
  // handles the label strikethrough immediately on status change; here we just
  // read the flag to decide whether to lock actions after the list renders.
  const chaptersExist = currentProject.status === 'split';
  _updateFootnotesTabState(); // ensure labels are in sync when tab is opened

  try {
    const [data, auditData] = await Promise.all([
      apiFetch('GET', `/projects/${currentProject.id}/footnotes/map`),
      apiFetch('GET', `/projects/${currentProject.id}/footnotes/audit`).catch(() => ({ issues: [], total_issues: 0 })),
    ]);
    const footnotes = data.footnotes || [];
    if (!footnotes.length) {
      list.innerHTML = '<div class="split-list-empty">No footnotes detected.<br>Run detection in Overview first.</div>';
      return;
    }

    // Build issue map: display_num → issue
    const issueMap = new Map();
    (auditData.issues || []).forEach(i => issueMap.set(i.display_num, i));

    // Issues button
    const totalIssues = auditData.total_issues || 0;
    if (totalIssues > 0) {
      issuesBtn.textContent = `Issues ⚠ ${totalIssues}`;
      issuesBtn.style.display = 'inline-block';
      issuesBtn._filterActive = issuesFilterActive;
      _applyIssuesButtonStyle(issuesBtn);
      issuesBtn.onclick = () => {
        issuesBtn._filterActive = !issuesBtn._filterActive;
        issuesFilterActive = issuesBtn._filterActive;
        _applyIssuesButtonStyle(issuesBtn);
        _applyIssuesFilter(list, issueMap, issuesFilterActive);
      };
    } else {
      issuesBtn._filterActive = false;
      _applyIssuesFilter(list, issueMap, false);
    }

    list.innerHTML = '';

    function makeAddZone(insertAfterNum) {
      const zone = document.createElement('div');
      zone.className = 'fn-add-zone';
      zone.dataset.insertAfter = insertAfterNum;
      zone.innerHTML = '<span class="fn-add-plus">+</span>';
      const form = document.createElement('div');
      form.className = 'fn-add-form';
      form.innerHTML = `
        <div class="fn-context-display" style="display:none"></div>
        <textarea class="fn-add-textarea" placeholder="Footnote content…" style="display:none"></textarea>
        <div class="fn-add-controls" style="display:none">
          <button class="btn primary" style="font-size:0.7rem;padding:0.2rem 0.5rem">Save</button>
          <button class="btn" style="font-size:0.7rem;padding:0.2rem 0.5rem">Cancel</button>
        </div>
      `;
      zone.addEventListener('click', () => {
        if (fnPickActive && fnPickZoneEl === zone) {
          deactivatePickMode();
          return;
        }
        activatePickMode(zone, insertAfterNum);
        console.log('[fn] pick mode activated, insertAfterNum:', insertAfterNum, 'fnPickActive:', fnPickActive);
      });
      const cancelBtn = form.querySelectorAll('.fn-add-controls .btn')[1];
      const saveBtn   = form.querySelector('.fn-add-controls .btn.primary');
      cancelBtn.addEventListener('click', () => {
        deactivatePickMode();
        form.classList.remove('visible');
        form.querySelector('.fn-context-display').style.display = 'none';
        form.querySelector('.fn-add-textarea').style.display = 'none';
        form.querySelector('.fn-add-controls').style.display = 'none';
      });
      saveBtn.addEventListener('click', () => saveNewFootnote(zone, insertAfterNum));
      return { zone, form };
    }

    // Add top zone (before #1)
    const topZone = makeAddZone(0);
    list.appendChild(topZone.zone);
    list.appendChild(topZone.form);

    footnotes.forEach(fn => {
      const el = document.createElement('div');
      el.className = 'fn-review-item';
      el.dataset.fnNum = fn.display_num;
      const preview  = fn.paragraph_preview ? fn.paragraph_preview.slice(0, 60) + '…' : '—';
      const injected = fn.injected ? ' <span class="fn-review-badge">✓</span>' : '';
      const issue    = issueMap.get(fn.display_num);
      el.innerHTML = `
        <div class="fn-review-header">
          <span class="fn-review-num">#${fn.display_num}${injected}</span>
          <span class="fn-review-actions">
            <button class="fn-btn-pos" title="Move to new position" style="font-size:0.7rem;padding:0.15rem 0.35rem;border:1px solid var(--accent,#4a9eff);color:var(--accent,#4a9eff);background:transparent;border-radius:3px;cursor:pointer">POS</button>
            <button class="fn-btn-edit" title="Edit">✎</button>
            <button class="fn-btn-remove" title="Remove">✕</button>
          </span>
        </div>
        <div class="fn-review-preview">${preview}</div>
        <div class="fn-review-content">${fn.content || '—'}</div>
        ${issue ? `<div class="fn-review-issue" style="font-family:var(--mono);font-size:0.68rem;color:var(--amber,#b5820a);margin-top:0.25rem;padding:0.15rem 0">⚠ ${issue.type}: ${issue.detail}</div>` : ''}
        <div class="fn-review-edit-area" style="display:none">
          <textarea class="fn-edit-textarea">${fn.content || ''}</textarea>
          <div class="fn-edit-controls">
            <button class="btn primary fn-btn-save" style="font-size:0.7rem;padding:0.2rem 0.5rem">Save</button>
            <button class="btn fn-btn-cancel" style="font-size:0.7rem;padding:0.2rem 0.5rem">Cancel</button>
          </div>
        </div>
      `;

      // Scroll to marker on item click
      el.addEventListener('click', e => {
        if (e.target.closest('.fn-btn-pos, .fn-btn-edit, .fn-btn-remove, .fn-btn-save, .fn-btn-cancel, .fn-edit-textarea')) return;
        const marker = document.querySelector(`#split-text-area [data-fn="${fn.id}"]`);
        if (marker) {
          marker.scrollIntoView({ behavior: 'smooth', block: 'center' });
          marker.classList.add('fn-marker-highlight');
          setTimeout(() => marker.classList.remove('fn-marker-highlight'), 1500);
        }
      });

      // POS — move mode
      el.querySelector('.fn-btn-pos').addEventListener('click', () => {
        if (fnMoveActive && fnMoveDisplayNum === fn.display_num) {
          deactivateMoveMode();
          return;
        }
        deactivatePickMode();
        fnMoveActive     = true;
        fnMoveDisplayNum = fn.display_num;
        fnMoveBtn        = el.querySelector('.fn-btn-pos');
        fnMoveBtn.classList.add('move-active');
        fnMoveBtn.style.background = 'var(--accent,#4a9eff)';
        fnMoveBtn.style.color      = '#fff';
        // Scroll to and highlight current marker
        const marker = document.querySelector(`#split-text-area [data-fn="${fn.id}"]`);
        if (marker) {
          marker.scrollIntoView({ behavior: 'smooth', block: 'center' });
          marker.classList.add('fn-marker-highlight');
        }
      });

      // Edit
      el.querySelector('.fn-btn-edit').addEventListener('click', () => {
        el.querySelector('.fn-review-content').style.display  = 'none';
        el.querySelector('.fn-review-edit-area').style.display = 'block';
        el.querySelector('.fn-edit-textarea').focus();
      });

      // Cancel
      el.querySelector('.fn-btn-cancel').addEventListener('click', () => {
        el.querySelector('.fn-edit-textarea').value           = fn.content || '';
        el.querySelector('.fn-review-content').style.display  = 'block';
        el.querySelector('.fn-review-edit-area').style.display = 'none';
      });

      // Save
      el.querySelector('.fn-btn-save').addEventListener('click', async () => {
        const newContent = el.querySelector('.fn-edit-textarea').value.trim();
        try {
          await apiFetch('PATCH', `/projects/${currentProject.id}/footnotes/${fn.display_num}`, { content: newContent });
          fn.content = newContent;
          el.querySelector('.fn-review-content').textContent   = newContent || '—';
          el.querySelector('.fn-review-content').style.display  = 'block';
          el.querySelector('.fn-review-edit-area').style.display = 'none';
        } catch(e) {
          alert('Failed to save: ' + e.message);
        }
      });

      // Remove
      el.querySelector('.fn-btn-remove').addEventListener('click', async () => {
        if (!confirm(`Remove footnote #${fn.display_num}?`)) return;
        const removedNum = fn.display_num;
        try {
          await apiFetch('DELETE', `/projects/${currentProject.id}/footnotes/${removedNum}`);
          await loadFullXhtml();
          await loadFootnotesReview();
          const list = document.getElementById('footnotes-review-list');
          const items = list.querySelectorAll('.fn-review-item');
          if (items.length) {
            const targetIdx = Math.min(removedNum - 1, items.length - 1);
            const targetItem = items[targetIdx];
            targetItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const targetFnNum = targetIdx + 1;
            const allSpans = document.querySelectorAll(`#split-text-area .fn-marker`);
            for (const span of allSpans) {
              if (span.getAttribute('data-display') === String(targetFnNum)) {
                span.scrollIntoView({ behavior: 'smooth', block: 'center' });
                span.classList.add('fn-marker-highlight');
                setTimeout(() => span.classList.remove('fn-marker-highlight'), 1500);
                break;
              }
            }
          }
        } catch(e) {
          alert('Failed to remove: ' + e.message);
        }
      });

      list.appendChild(el);

      // Add zone after each footnote
      const { zone, form } = makeAddZone(fn.display_num);
      list.appendChild(zone);
      list.appendChild(form);
    });

    // Apply filter if it was active before reload
    // if (issuesFilterActive) _applyIssuesFilter(list, issueMap, true);
    // Apply filter if it was active before reload
    if (issuesFilterActive && totalIssues > 0) _applyIssuesFilter(list, issueMap, true);
    else _applyIssuesFilter(list, issueMap, false);

    // #17: If chapters exist (status === 'split'), lock the entire footnotes panel.
    // Disable POS / Edit / Remove on every item. Hide all add-zones.
    // Issues toggle is intentionally left untouched.
    if (chaptersExist) {
      list.querySelectorAll('.fn-btn-pos, .fn-btn-edit, .fn-btn-remove').forEach(btn => {
        btn.disabled = true;
        btn.style.opacity = '0.25';
        btn.style.cursor  = 'default';
        btn.style.pointerEvents = 'none';
      });
      list.querySelectorAll('.fn-add-zone, .fn-add-form').forEach(el => {
        el.style.display = 'none';
      });
    }

  } catch(e) {
    list.innerHTML = '<div class="split-list-empty">No footnotes detected.<br>Run detection in Overview first.</div>';
  }
}

function _applyIssuesButtonStyle(btn) {
  if (btn._filterActive) {
    btn.style.opacity    = '1';
    btn.style.background = 'var(--amber, #b5820a)';
    btn.style.color      = '#fff';
    btn.style.border     = '1px solid var(--amber, #b5820a)';
  } else {
    btn.style.opacity    = '0.4';
    btn.style.background = 'transparent';
    btn.style.color      = 'var(--text2)';
    btn.style.border     = '1px solid var(--border)';
  }
}

function _applyIssuesFilter(list, issueMap, active) {
  list.querySelectorAll('.fn-review-item').forEach(el => {
    const num = parseInt(el.dataset.fnNum, 10);
    el.style.display = (!active || issueMap.has(num)) ? '' : 'none';
  });
  list.querySelectorAll('.fn-add-zone, .fn-add-form').forEach(el => {
    el.style.display = active ? 'none' : '';
  });
}