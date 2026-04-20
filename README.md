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
│   ├── background.js
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
3. Click **🎯 Annotate** to enter annotation mode. The popup will close automatically so you can interact with the page.
4. Hover over elements on the page — they will be highlighted with a dashed amber outline as you move the cursor.
5. Click an element to open the annotation dialog. Enter your instruction and click **Save Annotation** (or press `Ctrl+Enter` / `Cmd+Enter`).
6. A yellow sticky note overlay will appear next to the element, showing the CSS selector and your comment.
7. Open the popup again to see all annotations for the current page.
8. Use the **✏️** button on any card to edit an annotation inline, or **✕ Delete** to remove it.
9. Click **✨ Export Prompts** to send all annotations to the local Flask server.
10. The export panel will appear with three tabs:
    - **Plain Text** — a numbered instruction list suitable for pasting into any AI chat.
    - **XML Prompt** — a structured XML document for AI agents like Claude or Cursor.
    - **JSON Schema** — a machine-readable representation for programmatic use.
11. Click **📋 Copy** on any tab to copy that format to your clipboard, then paste it into your AI coding agent.

> **Tip:** Press `Esc` at any time while in annotation mode to exit without annotating, or to dismiss an open annotation dialog.

---

## API Endpoints

The Flask server exposes the following endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/export` | Accepts a JSON body with annotations and returns all prompt formats |

### `GET /health`

```bash
curl http://localhost:5000/health
```

Response:

```json
{"status": "ok"}
```

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

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `page_url` | string | ✅ | Full HTTP/HTTPS URL of the annotated page |
| `annotations` | array | ✅ | List of annotation objects (may be empty) |
| `annotations[].element_selector` | string | ✅ | CSS selector for the annotated element |
| `annotations[].comment` | string | ✅ | Developer instruction for the element |
| `annotations[].page_url` | string | ✅ | URL of the page (should match top-level `page_url`) |
| `annotations[].annotation_id` | string | ❌ | Optional unique ID assigned by the extension |
| `annotations[].html_context` | string | ❌ | Surrounding HTML snippet for context |

### `POST /export` response body

On success (HTTP 200):

```json
{
  "page_url": "https://example.com/dashboard",
  "annotation_count": 1,
  "plain_text": "PAGE ANNOTATION INSTRUCTIONS\n============================\n...",
  "xml_prompt": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<task>...</task>",
  "json_schema": {
    "schema_version": "1.0",
    "page_url": "https://example.com/dashboard",
    "annotation_count": 1,
    "annotations": [
      {
        "annotation_id": "uuid-1234",
        "element_selector": "#submit-btn",
        "html_context": "<button id=\"submit-btn\" class=\"btn\">Submit</button>",
        "instruction": "Change the button colour to green and add a loading spinner on click."
      }
    ]
  }
}
```

On error (HTTP 400):

```json
{
  "error": "<human-readable description of the problem>"
}
```

---

## Prompt Formats Explained

### Plain Text

A numbered instruction list designed for pasting directly into a chat window with any AI assistant (ChatGPT, Claude, Gemini, etc.):

```
PAGE ANNOTATION INSTRUCTIONS
============================
Page URL: https://example.com/dashboard
Total annotations: 1

Instructions:

1. Element: #submit-btn
   Annotation ID: uuid-1234
   HTML context:
     <button id="submit-btn" class="btn">Submit</button>
   Instruction: Change the button colour to green and add a loading spinner on click.
```

### XML Prompt

A structured XML document suited to AI coding agents (Claude, Cursor) that understand hierarchical context tags:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<task>
  <metadata>
    <page_url>https://example.com/dashboard</page_url>
    <annotation_count>1</annotation_count>
  </metadata>
  <annotations>
    <annotation id="uuid-1234">
      <element_selector>#submit-btn</element_selector>
      <html_context>&lt;button id="submit-btn" class="btn"&gt;Submit&lt;/button&gt;</html_context>
      <instruction>Change the button colour to green and add a loading spinner on click.</instruction>
    </annotation>
  </annotations>
</task>
```

### JSON Schema

A machine-readable dictionary for programmatic use by other tools or scripts:

```json
{
  "schema_version": "1.0",
  "page_url": "https://example.com/dashboard",
  "annotation_count": 1,
  "annotations": [
    {
      "annotation_id": "uuid-1234",
      "element_selector": "#submit-btn",
      "html_context": "<button id=\"submit-btn\" class=\"btn\">Submit</button>",
      "instruction": "Change the button colour to green and add a loading spinner on click."
    }
  ]
}
```

---

## Running Tests

Make sure the virtual environment is active and dependencies are installed, then run:

```bash
pytest
```

Verbose output with individual test names:

```bash
pytest -v
```

Run only unit tests (prompt builder):

```bash
pytest tests/test_prompt_builder.py -v
```

Run only integration tests (Flask API):

```bash
pytest tests/test_app.py -v
```

Run with coverage (requires `pytest-cov`):

```bash
pip install pytest-cov
pytest --cov=server --cov-report=term-missing
```

---

## Development Notes

### Server

- All server-side logic lives in the `server/` Python package.
- `server/models.py` — `Annotation` and `PromptExport` dataclasses with validation.
- `server/prompt_builder.py` — core prompt generation logic (plain text, XML, JSON).
- `server/app.py` — Flask application factory (`create_app`) and route definitions.
- The app uses the **application factory pattern** so tests can create isolated instances.
- CORS is enabled for all origins (`*`) so the Chrome extension popup (running on a `chrome-extension://` origin) can reach the local server.

### Extension

- The extension uses **Manifest V3** with a background service worker (`background.js`) and a content script (`content.js`).
- Annotations are stored per-page in `chrome.storage.session` and are cleared automatically when the browser session ends.
- All injected UI elements use the `pp-` CSS class prefix to minimise collisions with host-page styles.
- The content script computes CSS selectors automatically: it prefers `#id` selectors and falls back to a tag + class + `:nth-child` ancestor path.

### Changing the Server Port

If you need to run the server on a port other than `5000`:

1. Update the `SERVER_BASE_URL` constant at the top of `extension/popup.js`.
2. Update the `host_permissions` entry in `extension/manifest.json`.
3. Reload the extension in `chrome://extensions`.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Could not reach the local server" | Ensure the Flask server is running: `python -m flask --app server.app run --port 5000` |
| "Cannot annotate this page" | Chrome restricts content scripts on `chrome://`, `chrome-extension://`, and the Web Store. Try any regular `http://` or `https://` page. |
| Sticky notes disappear on page reload | This is expected for hard reloads that clear session storage. Annotations stored via `chrome.storage.session` persist across soft reloads within the same browser session. |
| Extension not appearing after load | Make sure **Developer mode** is enabled in `chrome://extensions` and that you selected the `extension/` directory (not the project root). |
| `ModuleNotFoundError: No module named 'server'` | Run pytest from the project root directory, not from inside `server/` or `tests/`. |

---

## License

MIT
