'use strict';

// ── DOM event wiring ──────────────────────────────────────────────────────────
// All inline onclick/onblur/oninput/onchange/onkeydown attributes have been
// removed from index.html and centralised here. Scripts load at end of <body>
// so the DOM is fully parsed — no DOMContentLoaded needed.

// ── Navigation ────────────────────────────────────────────────────────────────
// All nav items carry data-panel; handled with a single loop.
document.querySelectorAll('.nav-item[data-panel]').forEach(btn => {
  btn.addEventListener('click', () => showPanel(btn.dataset.panel));
});
document.getElementById('btn-get-started').addEventListener('click', () => showPanel('upload'));

// ── Upload ────────────────────────────────────────────────────────────────────
document.getElementById('tab-docx').addEventListener('click', () => setUploadMode('docx'));
document.getElementById('tab-epub').addEventListener('click', () => setUploadMode('epub'));
document.getElementById('input-project-id').addEventListener('input', function () {
  this.value = this.value.toLowerCase().replace(/[^a-z0-9-]/g, '');
});
document.getElementById('upload-area').addEventListener('click', onUploadAreaClick);
document.getElementById('upload-area').addEventListener('dragover', onUploadDragover);
document.getElementById('upload-area').addEventListener('dragleave', onUploadDragleave);
document.getElementById('upload-area').addEventListener('drop', onUploadDrop);
document.getElementById('file-input').addEventListener('change', onFileInputChange);
document.getElementById('btn-upload').addEventListener('click', uploadManuscript);

// ── Editor panel ──────────────────────────────────────────────────────────────
document.getElementById('btn-lt-check').addEventListener('click', checkGrammar);
document.getElementById('btn-insert-fn').addEventListener('click', showFootnoteInsertDialog);
document.getElementById('btn-preview-mode-toggle').addEventListener('click', togglePreviewMode);
document.getElementById('btn-ignore-panel').addEventListener('click', toggleIgnorePanel);
document.getElementById('btn-ignore-close').addEventListener('click', toggleIgnorePanel);
document.getElementById('btn-save-chapter').addEventListener('click', saveChapter);
document.getElementById('btn-format-xhtml').addEventListener('click', formatXhtml);
document.getElementById('btn-auto-split').addEventListener('click', autoSplitDetect);
document.getElementById('btn-apply-splits').addEventListener('click', applySplits);
document.getElementById('btn-clear-splits').addEventListener('click', clearAllSplits);
document.getElementById('btn-split-tab-splits').addEventListener('click', showSplitsView);
document.getElementById('btn-split-tab-footnotes').addEventListener('click', showFootnotesView);
document.getElementById('btn-bold').addEventListener('click', () => applyFormat('b'));
document.getElementById('btn-italic').addEventListener('click', () => applyFormat('i'));
document.getElementById('btn-monaco-fs-up').addEventListener('click', monacoFsUp);
document.getElementById('btn-monaco-fs-down').addEventListener('click', monacoFsDown);
document.getElementById('editor-content').addEventListener('input', onEditorContentInput);
document.getElementById('editor-content').addEventListener('keyup', updateFormatButtons);
document.getElementById('editor-content').addEventListener('mouseup', updateFormatButtons);
document.getElementById('editor-content').addEventListener('selectionchange', updateFormatButtons);
document.getElementById('preview-pane-body').addEventListener('click', onPreviewLtClick);
document.getElementById('preview-pane-body').addEventListener('click', onPreviewClick);
document.addEventListener('keydown', onEditorKeydown);
document.addEventListener('keydown', onDocumentFormatKeydown);
document.addEventListener('click', onDocumentClickHidePopover);

// ── Build panel ───────────────────────────────────────────────────────────────
document.getElementById('build-tab-digital').addEventListener('click', () => setBuildProfile('digital'));
document.getElementById('build-tab-print').addEventListener('click', () => setBuildProfile('print'));
document.getElementById('btn-add-front').addEventListener('click', () => addBuildItem('front'));
document.getElementById('btn-add-chapter').addEventListener('click', addBuildChapter);
// document.getElementById('btn-save-chapters').addEventListener('click', saveChapters);
document.getElementById('btn-add-back').addEventListener('click', () => addBuildItem('back'));
document.getElementById('btn-build-preview-edit').addEventListener('click',
  () => openBuildItemInEditor().catch(e => console.error('openBuildItemInEditor error:', e)));

// ── Images & footnotes ────────────────────────────────────────────────────────
document.getElementById('image-upload-input').addEventListener('change', e => uploadImage(e.target));
document.getElementById('footnote-upload-input').addEventListener('change', e => uploadFootnotes(e.target));
document.getElementById('fn-variant-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') addFnVariant();
});
document.getElementById('btn-add-fn-variant').addEventListener('click', addFnVariant);
document.getElementById('btn-delete-footnotes').addEventListener('click', deleteFootnotes);

// ── Build metadata ────────────────────────────────────────────────────────────
document.getElementById('build-author').addEventListener('blur', function () { saveMetaField('author', this.value); });
document.getElementById('build-language').addEventListener('blur', function () { saveMetaField('language', this.value); });
document.getElementById('build-publisher').addEventListener('blur', function () { saveMetaField('publisher', this.value); });

// ── Build actions ─────────────────────────────────────────────────────────────
document.getElementById('btn-hyphenate').addEventListener('click', hyphenateChapters);
document.getElementById('btn-dehyphenate').addEventListener('click', dehyphenateChapters);
document.getElementById('btn-build-epub').addEventListener('click', buildEpub);
document.getElementById('btn-add-css').addEventListener('click', addNewCss);
document.getElementById('btn-reset-build').addEventListener('click', resetBuildConfig);

// ── Project management ────────────────────────────────────────────────────────
document.getElementById('btn-reset-project').addEventListener('click', resetProject);
document.getElementById('btn-delete-project').addEventListener('click', deleteProject);
document.getElementById('btn-detect-footnotes').addEventListener('click', detectFootnotes);
document.getElementById('btn-reset-footnotes').addEventListener('click', resetFootnotes);
document.getElementById('btn-inject-footnotes').addEventListener('click', injectFootnotes);

// ── Dialogs & popovers ────────────────────────────────────────────────────────
document.getElementById('btn-close-fn-dialog').addEventListener('click', closeFnDialog);
document.getElementById('fn-dialog-overlay').addEventListener('click', closeFnDialog);
document.getElementById('pop-ignore-btn').addEventListener('click', ignoreCurrentWord);
document.getElementById('pop-ignore-rule-btn').addEventListener('click', ignoreCurrentRule);
// ── PDF Tools ─────────────────────────────────────────────────────────────────
document.getElementById('btn-convert-pdf').addEventListener('click', goToPdfTools);
document.getElementById('btn-build-toc').addEventListener('click', buildToc);
document.getElementById('btn-pdf-save-config').addEventListener('click', savePdfConfig);
document.getElementById('btn-pdf-convert').addEventListener('click', convertToPdf);