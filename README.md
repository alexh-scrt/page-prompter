# page_prompter

**page_prompter** is a browser extension that lets developers annotate live web pages with sticky notes and structured instructions, then exports them as formatted prompts ready for AI coding agents like Codex, Claude, or Cursor.

Click any element on a page, attach a comment describing the desired change or behaviour, and instantly generate a structured, context-rich prompt that includes element selectors, the page URL, and surrounding HTML context — making it easy to give precise, unambiguous instructions to AI agents.

---

## Features

- **Click-to-annotate** any DOM element on a live web page with a sticky note overlay showing the CSS selector and your comment.
- **Popup panel** listing all annotations for the current page with edit and delete capabilities.
- **One-click prompt export** that includes the page URL, element selectors, surrounding HTML snippets, and developer instructions.
- **Multiple prompt formats**: plain instruction list, XML-tagged agent prompt, and JSON schema for programmatic use.
- **Session persistence**: Annotations are stored via `chrome.storage.session` so they survive page reloads during a development session.

---

## Project Structure

```
page_prompter/
├── extension/          # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── content.js
│   ├── popup.html
│   ├── popup.js
│   └── styles.css
├── server/             # Flask API server
│   ├── __init__.py
│   ├── app.py
│   ├── models.py
│   └── prompt_builder.py
├── tests/              # pytest test suite
│   ├── test_app.py
│   └── test_prompt_builder.py
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python 3.10 or later
- Google Chrome (or any Chromium-based browser that supports Manifest V3)
- pip

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-org/page_prompter.git
cd page_prompter
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the Flask server

```bash
python -m flask --app server.app run --port 5000
```

The server will be available at `http://localhost:5000`.

> **Note:** The extension expects the server to be running on `http://localhost:5000`. Do not change the port without also updating `popup.js`.

### 5. Load the Chrome extension

1. Open Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked**.
4. Select the `extension/` directory from this repository.

The page_prompter icon will appear in your toolbar.

---

## Usage

1. Navigate to any web page you want to annotate.
2. Click the **page_prompter** toolbar icon to open the popup.
3. Click **Start Annotating** to enter annotation mode.
4. Hover over elements on the page — they will be highlighted as you move the cursor.
5. Click an element to open the annotation dialog. Enter your instruction and confirm.
6. A sticky note overlay will appear on the element showing the CSS selector and your comment.
7. Open the popup again to see all annotations for the current page.
8. Click **Export Prompts** to send all annotations to the local Flask server and receive a structured prompt.
9. The prompt is copied to your clipboard automatically, ready to paste into your AI coding agent.

---

## API Endpoints

The Flask server exposes the following endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/export` | Accepts a JSON array of annotations and returns all prompt formats |

### `POST /export` request body

```json
{
  "page_url": "https://example.com/dashboard",
  "annotations": [
    {
      "annotation_id": "uuid-1234",
      "element_selector": "#submit-btn",
      "comment": "Change the button colour to green and add a loading spinner on click.",
      "html_context": "<button id=\"submit-btn\" class=\"btn\">Submit</button>"
    }
  ]
}
```

### `POST /export` response body

```json
{
  "page_url": "https://example.com/dashboard",
  "annotation_count": 1,
  "plain_text": "...",
  "xml_prompt": "...",
  "json_schema": { ... }
}
```

---

## Running Tests

```bash
pytest
```

Or with verbose output:

```bash
pytest -v
```

---

## Development Notes

- All server-side logic is in the `server/` package.
- `server/models.py` contains the `Annotation` and `PromptExport` dataclasses.
- `server/prompt_builder.py` contains the core prompt generation logic.
- `server/app.py` contains the Flask application and route definitions.
- The extension uses **Manifest V3** with a background service worker and a content script.
- Annotations are stored per-tab in `chrome.storage.session` and are cleared when the browser session ends.

---

## License

MIT
