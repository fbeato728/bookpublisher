# BookPublisher

A full-stack web application for creating, editing, and building digital books (EPUB) and print publications (PDF).

## Features

- **Project management** — create, import, and manage book projects
- **XHTML chapter editor** — Monaco-based editor with syntax highlighting
- **EPUB import** — import and convert existing EPUB files
- **Book metadata** — manage title, author, ISBN, translator, and other fields
- **Content splitting** — split raw content into organized chapters
- **Footnote management** — detect, edit, and inject footnotes
- **Image handling** — upload and optimize images
- **PDF generation** — via Prince PDF CLI with hyphenation and font support
- **Build profiles** — separate digital and print output configurations with different front/back matter
- **CSS token system** — dynamic styling via configurable CSS variables
- **Grammar/spell checking** — integrated LanguageTool support

## Tech Stack

**Backend:** Python 3, Flask, lxml, Pillow, python-docx

**Frontend:** Vanilla JavaScript, Monaco Editor, PDF.js

**External services:** LanguageTool (spell/grammar), Prince PDF CLI (PDF generation)

## Project Structure

```
bookpublisher/
├── backend/
│   ├── app.py              # Flask application entry point
│   ├── config.py           # Environment-based path configuration
│   ├── routes/             # API route blueprints
│   │   ├── projects.py     # Project CRUD and metadata
│   │   ├── build.py        # EPUB/PDF building and templating
│   │   ├── split.py        # Chapter splitting
│   │   ├── chapters.py     # Chapter management
│   │   ├── epub_import.py  # EPUB import
│   │   ├── xhtml.py        # XHTML validation
│   │   ├── footnotes.py    # Footnote detection and injection
│   │   ├── images.py       # Image processing
│   │   ├── fonts.py        # Font management
│   │   ├── pdf.py          # PDF generation
│   │   └── hyphenate.py    # Hyphenation
│   ├── scripts/
│   │   └── docx_converter.py  # DOCX to XHTML conversion
│   ├── templates/
│   │   └── index.html      # Single-page app shell
│   └── static/
│       ├── js/             # Frontend JavaScript modules
│       ├── css/            # Stylesheets
│       ├── pdfjs/          # PDF.js library
│       └── monaco/         # Monaco editor
└── global/
    ├── config/             # Build profiles, tokens, templates config
    ├── fonts/              # Shared typography fonts
    ├── styles/             # Global CSS stylesheets
    └── templates/          # Front/back matter templates
```

## Installation

### Requirements

- Python 3.8+
- [LanguageTool](https://languagetool.org/) running on port 8082 (optional, for spell/grammar checking)
- [Prince PDF](https://www.princexml.com/) CLI (optional, for PDF generation)

### Setup

```bash
# Clone the repository
git clone https://github.com/fbeato728/bookpublisher.git
cd bookpublisher

# Install Python dependencies
pip install -r requirements.txt
```

### Environment Variables

The application uses the following environment variables (with defaults):

| Variable | Default | Description |
|---|---|---|
| `BP_PROJECTS_DIR` | `/srv/bookpublisher/projects` | Where book projects are stored |
| `BP_GLOBAL_DIR` | `/srv/bookpublisher/global` | Shared assets and configuration |
| `BP_BUILDS_DIR` | `/srv/bookpublisher/builds` | Build output directory |

## Running

```bash
python backend/app.py
```

The application will be available at `http://localhost:5000`.

## API Endpoints

| Prefix | Description |
|---|---|
| `/api/projects/*` | Project CRUD operations |
| `/api/split/*` | Chapter splitting |
| `/api/chapters/*` | Chapter management |
| `/api/xhtml/*` | XHTML validation |
| `/api/epub-import` | EPUB file import |
| `/api/build/*` | EPUB/PDF building |
| `/api/images/*` | Image upload and processing |
| `/api/footnotes/*` | Footnote detection and management |
| `/api/hyphenate/*` | Hyphenation |
| `/api/fonts/*` | Font management |
| `/api/pdf/*` | PDF generation |
| `/api/check` | LanguageTool spell/grammar proxy |
| `/api/health` | Health check |

## Configuration

Key configuration files in `global/config/`:

- **`tokens.json`** — metadata field definitions (title, author, ISBN, translator, etc.)
- **`build.json`** — digital and print build profiles with front/back matter settings
- **`split.json`** — chapter naming patterns and XHTML templates
- **`css_tokens.json`** — CSS variable definitions for dynamic styling
- **`global.json`** — CSS override paths and Prince CLI configuration
