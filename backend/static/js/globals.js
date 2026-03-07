'use strict';

let currentProject     = null;
let splitElements      = [];
let splitMarkers       = [];
let splitSavedData     = [];
let splitProjectId     = null;
let currentChapterFile = null;
let ltMatches          = [];
let isDirty            = false;
let checking           = false;
let editorMode         = 'text';
let monacoEditor       = null;
let monacoReady        = false;
let monacoLoading      = false;   // guard: suppress isDirty during programmatic setValue
let uploadMode         = 'docx';
let fileIsHyphenated   = false;    // true when the loaded file contains soft hyphens
let previewVisible     = false;

// ── Cross-module state (declared here; owned across projects/build/editor) ────
let buildConfig        = null;
let chaptersDirty      = false;
let chaptersEditing    = [];       // working copy while editing chapter list
let currentStylesheet  = '../styles/main.css'; // href from the currently loaded file

