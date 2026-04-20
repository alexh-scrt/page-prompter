"""Flask API server for the page_prompter extension.

Exposes a minimal REST API that receives annotations from the page_prompter
Chrome extension and returns structured AI agent prompts in three formats:
plain text, XML-tagged, and JSON schema.

Endpoints
---------
GET  /health
    Returns ``{"status": "ok"}`` to confirm the server is reachable.

POST /export
    Accepts a JSON body with a ``page_url`` string and an ``annotations``
    array, validates the input, builds all prompt formats via
    :mod:`server.prompt_builder`, and returns the resulting
    :class:`~server.models.PromptExport` as JSON.

CORS is enabled for all origins so the extension's popup page (which runs
on a ``chrome-extension://`` origin) can reach the server without browser
blocking.

Usage::

    python -m flask --app server.app run --port 5000
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from server.models import Annotation, ValidationError
from server.prompt_builder import build_prompt_export

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application.

    Using an application factory makes the app easier to test: each test can
    instantiate a fresh app with ``TESTING=True`` without global side-effects.

    Args:
        test_config: Optional dictionary of Flask configuration overrides.  If
            provided, these values are loaded *after* the defaults so they take
            precedence.  Useful for passing ``{"TESTING": True}`` in the test
            suite.

    Returns:
        A configured :class:`flask.Flask` application instance.
    """
    app = Flask(__name__, instance_relative_config=False)

    # Default configuration
    app.config.setdefault("JSON_SORT_KEYS", False)

    if test_config is not None:
        app.config.update(test_config)

    # Enable CORS for all routes and all origins so the Chrome extension
    # (chrome-extension://* origin) can call the local server.
    CORS(app, resources={r"/*": {"origins": "*"}})

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health")
    def health() -> Response:
        """Health-check endpoint.

        Returns:
            200 JSON response ``{"status": "ok"}`` confirming the server is
            running and reachable.
        """
        return jsonify({"status": "ok"})

    @app.post("/export")
    def export_prompt() -> tuple[Response, int]:
        """Build and return structured prompts from a list of annotations.

        Request body (JSON)
        -------------------
        .. code-block:: json

            {
              "page_url": "https://example.com/dashboard",
              "annotations": [
                {
                  "annotation_id": "uuid-1234",
                  "element_selector": "#submit-btn",
                  "comment": "Change the button colour to green.",
                  "html_context": "<button id=\\"submit-btn\\">Submit</button>"
                }
              ]
            }

        Response body (JSON)
        --------------------
        On success (HTTP 200):

        .. code-block:: json

            {
              "page_url": "https://example.com/dashboard",
              "annotation_count": 1,
              "plain_text": "...",
              "xml_prompt": "...",
              "json_schema": { ... }
            }

        On error (HTTP 400):

        .. code-block:: json

            {
              "error": "<human-readable description>"
            }

        Returns:
            A ``(Response, status_code)`` tuple.  Status is 200 on success,
            400 for client errors (bad JSON, missing fields, validation
            failures).
        """
        # ---- Parse request body ------------------------------------------
        if not request.is_json:
            return (
                jsonify({"error": "Request Content-Type must be application/json."}),
                400,
            )

        payload: Any = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "Request body is not valid JSON."}), 400

        if not isinstance(payload, dict):
            return (
                jsonify({"error": "Request body must be a JSON object."}),
                400,
            )

        # ---- Extract page_url --------------------------------------------
        page_url = payload.get("page_url")
        if page_url is None:
            return jsonify({"error": "Missing required field: 'page_url'."}), 400

        if not isinstance(page_url, str) or not page_url.strip():
            return (
                jsonify({"error": "'page_url' must be a non-empty string."}),
                400,
            )

        # ---- Extract annotations list ------------------------------------
        raw_annotations = payload.get("annotations")
        if raw_annotations is None:
            return (
                jsonify({"error": "Missing required field: 'annotations'."}),
                400,
            )

        if not isinstance(raw_annotations, list):
            return (
                jsonify({"error": "'annotations' must be a JSON array."}),
                400,
            )

        # ---- Deserialise each annotation ---------------------------------
        annotations: list[Annotation] = []
        for index, item in enumerate(raw_annotations):
            if not isinstance(item, dict):
                return (
                    jsonify(
                        {
                            "error": (
                                f"Item at index {index} in 'annotations' must be "
                                f"a JSON object."
                            )
                        }
                    ),
                    400,
                )
            try:
                annotation = Annotation.from_dict(item)
            except ValidationError as exc:
                return (
                    jsonify(
                        {
                            "error": (
                                f"Annotation at index {index} is invalid: {exc}"
                            )
                        }
                    ),
                    400,
                )

            annotations.append(annotation)

        # ---- Build prompt export -----------------------------------------
        try:
            prompt_export = build_prompt_export(page_url, annotations)
        except ValidationError as exc:
            log.warning("Prompt build validation error: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except TypeError as exc:
            log.warning("Prompt build type error: %s", exc)
            return jsonify({"error": str(exc)}), 400

        return jsonify(prompt_export.to_dict()), 200

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(error: Any) -> tuple[Response, int]:
        """Return a JSON 404 response instead of the default HTML page."""
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(error: Any) -> tuple[Response, int]:
        """Return a JSON 405 response instead of the default HTML page."""
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(500)
    def internal_server_error(error: Any) -> tuple[Response, int]:
        """Return a JSON 500 response for unexpected server errors."""
        log.exception("Internal server error")
        return jsonify({"error": "Internal server error."}), 500

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (used by `flask run` and gunicorn)
# ---------------------------------------------------------------------------

#: Module-level Flask application instance.  Created once at import time so
#: that ``flask --app server.app run`` and WSGI servers (gunicorn, etc.) can
#: discover and serve it directly.
app: Flask = create_app()
