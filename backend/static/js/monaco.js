'use strict';

// ── Monaco editor initialisation ─────────────────────────────────────────────
// Depends on: monacoReady (globals.js), window.monacoFailed (set by loader onerror)

function initMonaco(cb) {
  console.log('initMonaco called and said hello... i am the original initMonaco');
  if (monacoReady) { cb(); return; }
  if (window.monacoFailed) { cb(new Error('Monaco not available')); return; }
  require.config({ paths: { vs: window.monacoBase } });
  require(['vs/editor/editor.main'], () => { monacoReady = true; cb(); });
}


// function initMonaco(cb) {
//   console.log('initMonaco called and said hello');
//   if (monacoReady) { cb(); return; }
//   if (window.monacoFailed) { cb(new Error('Monaco not available')); return; }

//   require.config({ paths: { vs: window.monacoBase } });

// require(['vs/editor/editor.main'], () => {
//     console.log('Monaco ready - Forcing XHTML compatibility');
//     monacoReady = true;

//     // 1. THE BRAIN FIX: Tell the HTML worker to stop "cleaning" void tags
//     // This is the ONLY way to keep the / in <img />
//     monaco.languages.html.htmlDefaults.setOptions({
//         format: {
//             // This list tells the formatter: "Treat these as unformatted blocks"
//             // It prevents the removal of the trailing slash ( /> )
//             unformatted: 'img, br, hr, input, link, meta',
//             contentUnformatted: 'img, br, hr, input, link, meta'
//         },
//         validate: false // Stops it from complaining that /> isn't standard HTML5
//     });

//     // 2. THE UI FIX: Stop the editor from injecting </img>
//     // This overrides the 'html' language rules globally
//     monaco.languages.setLanguageConfiguration('html', {
//         autoClosingPairs: [
//             { open: '<', close: '>' },
//             { open: '"', close: '"' },
//             { open: "'", close: "'" }
//         ],
//         // This stops the editor from thinking <img> is an "open" tag
//         onEnterRules: [] 
//     });

//     cb();
// });
// }




