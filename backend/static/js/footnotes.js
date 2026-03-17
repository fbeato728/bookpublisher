'use strict';

const FN_CONTEXT_CHARS = 50;
let fnPickActive      = false;
let fnPickInsertAfter = null; // display_num after which to insert
let fnPickZoneEl      = null; // the active .fn-add-zone element
let fnPickData        = null; // { xhtmlIndex, charOffset }

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
}

function onFootnotePickClick(e, xhtmlIndex, wrapper) {
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

async function loadFootnotesReview() {
  const list = document.getElementById('footnotes-review-list');
  list.innerHTML = '<div class="split-list-empty">Loading…</div>';

  if (!currentProject) {
    list.innerHTML = '<div class="split-list-empty">No project open.</div>';
    return;
  }

  try {
    const data = await apiFetch('GET', `/projects/${currentProject.id}/footnotes/map`);
    const footnotes = data.footnotes || [];
    if (!footnotes.length) {
      list.innerHTML = '<div class="split-list-empty">No footnotes detected.<br>Run detection in Overview first.</div>';
      return;
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
      const preview  = fn.paragraph_preview ? fn.paragraph_preview.slice(0, 60) + '…' : '—';
      const injected = fn.injected ? ' <span class="fn-review-badge">✓</span>' : '';
      el.innerHTML = `
        <div class="fn-review-header">
          <span class="fn-review-num">#${fn.display_num}${injected}</span>
          <span class="fn-review-actions">
            <button class="fn-btn-edit" title="Edit">✎</button>
            <button class="fn-btn-remove" title="Remove">✕</button>
          </span>
        </div>
        <div class="fn-review-preview">${preview}</div>
        <div class="fn-review-content">${fn.content || '—'}</div>
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
        if (e.target.closest('.fn-btn-edit, .fn-btn-remove, .fn-btn-save, .fn-btn-cancel, .fn-edit-textarea')) return;
        const marker = document.querySelector(`#split-text-area [data-fn="${fn.id}"]`);
        if (marker) {
          marker.scrollIntoView({ behavior: 'smooth', block: 'center' });
          marker.classList.add('fn-marker-highlight');
          setTimeout(() => marker.classList.remove('fn-marker-highlight'), 1500);
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
          // Scroll to the footnote now at the same position, or the last one
          const list = document.getElementById('footnotes-review-list');
          const items = list.querySelectorAll('.fn-review-item');
          if (items.length) {
            const targetIdx = Math.min(removedNum - 1, items.length - 1);
            const targetItem = items[targetIdx];
            targetItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // Also scroll text area to that marker
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
  } catch(e) {
    list.innerHTML = '<div class="split-list-empty">No footnotes detected.<br>Run detection in Overview first.</div>';
  }
}