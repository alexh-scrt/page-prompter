# page_prompter

> Annotate any web page, export precision prompts for AI coding agents — in seconds.

**page_prompter** is a Chrome extension that lets developers click any element on a live web page, attach a sticky note describing the desired change, and instantly generate a structured, context-rich prompt ready for AI coding agents like Codex, Claude, or Cursor. Each exported prompt includes the page URL, CSS selectors, surrounding HTML snippets, and your instructions — giving AI agents everything they need to act precisely.

---

## Quick Start

### 1. Start the local Flask server

```bash
# Clone the repo
git clone https://github.com/your-org/page_prompter.git
cd page_prompter

# Install Python dependencies
pip install -r requirements.txt

# Start the server
flask --app server.app run
# Server runs at http://localhost:5000
```

### 2. Load the Chrome extension

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** and select the `extension/` folder
4. The page_prompter icon appears in your toolbar

### 3. Annotate a page and export

1. Visit any web page
2. Click the **page_prompter** toolbar icon
3. Click **Start Annotating**, then click any element on the page
4. Type your instruction in the sticky note dialog and save
5. Open the popup, click **Export Prompt**, then copy your preferred format

---

## Features

- **Click-to-annotate** — Click any DOM element on a live page to attach a sticky note overlay showing the CSS selector and your comment.
- **Popup annotation panel** — View, edit, and delete all annotations for the current page in one place.
- **One-click structured export** — Generate prompts that include the page URL, element selectors, surrounding HTML context, and your instructions.
- **Multiple prompt formats** — Choose from a plain instruction list, an XML-tagged agent prompt (ideal for Claude/Cursor), or a JSON schema for programmatic use.
- **Session persistence** — Annotations are stored in `chrome.storage.session` and survive page reloads throughout your development session.

---

## Usage Examples

### Annotating an element

Click the **Start Annotating** button in the popup, hover over any element (it highlights with a dashed border), then click it. A dialog appears:

```
Element: #checkout-btn
URL:     https://myapp.dev/cart

Instruction: "Change button text to 'Complete Purchase' and
              make the background color #22c55e"
```

Save the note — a sticky label appears pinned to the element.

### Exported prompt formats

**Plain text**
```
Page: https://myapp.dev/cart

1. Element: #checkout-btn
   Selector: #checkout-btn
   Instruction: Change button text to 'Complete Purchase' and make the background color #22c55e
   HTML context: <button id="checkout-btn" class="btn btn-primary">Checkout</button>
```

**XML-tagged (Claude / Cursor)**
```xml
<task>
  <page_url>https://myapp.dev/cart</page_url>
  <annotations>
    <annotation index="1">
      <selector>#checkout-btn</selector>
      <instruction>Change button text to 'Complete Purchase' and make the background color #22c55e</instruction>
      <html_context><![CDATA[<button id="checkout-btn" class="btn btn-primary">Checkout</button>]]></html_context>
    </annotation>
  </annotations>
</task>
```

**JSON schema**
```json
{
  "page_url": "https://myapp.dev/cart",
  "annotations": [
    {
      "selector": "#checkout-btn",
      "instruction": "Change button text to 'Complete Purchase' and make the background color #22c55e",
      "html_context": "<button id=\"checkout-btn\" class=\"btn btn-primary\">Checkout</button>"
    }
  ]
}
```

### Calling the API directly

```bash
curl -X POST http://localhost:5000/export \
  -H "Content-Type: application/json" \
  -d '{
    "page_url": "https://myapp.dev/cart",
    "annotations": [
      {
        "element_selector": "#checkout-btn",
        "comment": "Change button text to Complete Purchase",
        "html_context": "<button id=\"checkout-btn\">Checkout</button>"
      }
    ]
  }'
```

```bash
# Health check
curl http://localhost:5000/health
# {"status": "ok"}
```

---

## Project Structure

```
page_prompter/
├── extension/
│   ├── manifest.json      # Chrome Extension Manifest V3 config
│   ├── background.js      # Service worker: lifecycle events & message relay
│   ├── content.js         # Injected script: element picking, sticky notes, storage
│   ├── popup.html         # Toolbar popup UI
│   ├── popup.js           # Popup logic: annotation list, export, clipboard
│   └── styles.css         # Injected overlay and annotation UI styles
├── server/
│   ├── __init__.py        # Package init
│   ├── app.py             # Flask API server (GET /health, POST /export)
│   ├── prompt_builder.py  # Core prompt generation logic
│   └── models.py          # Annotation and PromptExport dataclasses
├── tests/
│   ├── test_app.py        # Integration tests for Flask API endpoints
│   ├── test_prompt_builder.py  # Unit tests for prompt generation
│   └── test_models.py     # Unit tests for data models
├── requirements.txt
└── README.md
```

---

## Configuration

### Server port

By default the Flask server runs on `http://localhost:5000`. The extension's `manifest.json` grants host permissions to this address. To change the port:

```bash
flask --app server.app run --port 5001
```

Then update `extension/manifest.json` and `extension/popup.js` to match:

```json
// manifest.json
"host_permissions": ["http://localhost:5001/*"]
```

```js
// popup.js
const SERVER_URL = 'http://localhost:5001/export';
```

### Running tests

```bash
pytest

# With coverage
pytest --tb=short -v
```

### CORS

CORS is enabled for all origins by default (required for `chrome-extension://` origins). This is intentional — the server is local-only and never exposed to the internet.

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

> Built with [Jitter](https://github.com/jitter-ai) - an AI agent that ships code daily.
