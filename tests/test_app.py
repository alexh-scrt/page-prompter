"""Integration tests for the Flask API server (server/app.py).

Uses the pytest-flask ``client`` fixture to exercise every endpoint through
the real Flask test client so that routing, request parsing, CORS headers,
error handlers, and prompt generation all work end-to-end.

Coverage
--------
- GET  /health  – success
- POST /export  – success: empty annotations, single annotation, multiple
- POST /export  – 400 errors: non-JSON body, missing fields, bad types,
  invalid annotation data, invalid URL in annotation
- 404 / 405 error handlers
- CORS headers present on responses
- create_app factory behaviour
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from server.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> Flask:
    """Create a fresh Flask app configured for testing."""
    return create_app({"TESTING": True})


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Return a test client bound to the test app."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


VALID_ANNOTATION: dict[str, Any] = {
    "annotation_id": "uuid-0001",
    "element_selector": "#submit-btn",
    "comment": "Change the button colour to green.",
    "html_context": '<button id="submit-btn" class="btn">Submit</button>',
    "page_url": "https://example.com/dashboard",
}

PAGE_URL = "https://example.com/dashboard"


def post_export(
    client: FlaskClient,
    payload: Any,
    content_type: str = "application/json",
) -> Any:
    """Send a POST /export request and return the response."""
    if content_type == "application/json" and not isinstance(payload, (str, bytes)):
        data = json.dumps(payload)
    else:
        data = payload
    return client.post("/export", data=data, content_type=content_type)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for the GET /health endpoint."""

    def test_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_json(self, client: FlaskClient) -> None:
        response = client.get("/health")
        assert response.content_type.startswith("application/json")

    def test_status_ok(self, client: FlaskClient) -> None:
        response = client.get("/health")
        data = response.get_json()
        assert data["status"] == "ok"

    def test_post_health_returns_405(self, client: FlaskClient) -> None:
        response = client.post("/health")
        assert response.status_code == 405

    def test_put_health_returns_405(self, client: FlaskClient) -> None:
        response = client.put("/health")
        assert response.status_code == 405

    def test_delete_health_returns_405(self, client: FlaskClient) -> None:
        response = client.delete("/health")
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# POST /export – happy paths
# ---------------------------------------------------------------------------


class TestExportEndpointSuccess:
    """Tests for successful POST /export responses."""

    def test_empty_annotations_returns_200(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        response = post_export(client, payload)
        assert response.status_code == 200

    def test_empty_annotations_returns_json(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        response = post_export(client, payload)
        assert response.content_type.startswith("application/json")

    def test_empty_annotations_annotation_count_zero(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        data = post_export(client, payload).get_json()
        assert data["annotation_count"] == 0

    def test_response_contains_required_keys(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        data = post_export(client, payload).get_json()
        assert "page_url" in data
        assert "annotation_count" in data
        assert "plain_text" in data
        assert "xml_prompt" in data
        assert "json_schema" in data

    def test_response_page_url_matches_request(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        data = post_export(client, payload).get_json()
        assert data["page_url"] == PAGE_URL

    def test_single_annotation_returns_200(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        response = post_export(client, payload)
        assert response.status_code == 200

    def test_single_annotation_count(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert data["annotation_count"] == 1

    def test_single_annotation_plain_text_contains_selector(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert "#submit-btn" in data["plain_text"]

    def test_single_annotation_xml_prompt_contains_selector(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert "#submit-btn" in data["xml_prompt"]

    def test_single_annotation_json_schema_contains_selector(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        selectors = [
            a["element_selector"] for a in data["json_schema"]["annotations"]
        ]
        assert "#submit-btn" in selectors

    def test_multiple_annotations(self, client: FlaskClient) -> None:
        annotations = [
            {
                "annotation_id": f"uuid-{i}",
                "element_selector": f"#el-{i}",
                "comment": f"Instruction {i}.",
                "html_context": f'<div id="el-{i}">Content</div>',
                "page_url": PAGE_URL,
            }
            for i in range(3)
        ]
        payload = {"page_url": PAGE_URL, "annotations": annotations}
        data = post_export(client, payload).get_json()
        assert data["annotation_count"] == 3
        assert len(data["json_schema"]["annotations"]) == 3

    def test_annotation_without_optional_fields(self, client: FlaskClient) -> None:
        """Annotations without annotation_id or html_context are valid."""
        annotation = {
            "element_selector": "h1.title",
            "comment": "Make the font larger.",
            "page_url": PAGE_URL,
        }
        payload = {"page_url": PAGE_URL, "annotations": [annotation]}
        response = post_export(client, payload)
        assert response.status_code == 200

    def test_plain_text_is_string(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert isinstance(data["plain_text"], str)

    def test_xml_prompt_is_string(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert isinstance(data["xml_prompt"], str)

    def test_xml_prompt_has_task_element(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert "<task>" in data["xml_prompt"]

    def test_json_schema_is_dict(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [VALID_ANNOTATION]}
        data = post_export(client, payload).get_json()
        assert isinstance(data["json_schema"], dict)

    def test_json_schema_version(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        data = post_export(client, payload).get_json()
        assert data["json_schema"]["schema_version"] == "1.0"

    def test_plain_text_contains_page_url(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        data = post_export(client, payload).get_json()
        assert PAGE_URL in data["plain_text"]

    def test_xml_prompt_starts_with_declaration(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        data = post_export(client, payload).get_json()
        assert data["xml_prompt"].startswith("<?xml")

    def test_json_schema_annotation_count_matches(self, client: FlaskClient) -> None:
        annotations = [
            {
                "element_selector": f"#el-{i}",
                "comment": f"Do thing {i}.",
                "page_url": PAGE_URL,
            }
            for i in range(4)
        ]
        payload = {"page_url": PAGE_URL, "annotations": annotations}
        data = post_export(client, payload).get_json()
        assert data["json_schema"]["annotation_count"] == 4
        assert len(data["json_schema"]["annotations"]) == 4

    def test_comment_in_plain_text(self, client: FlaskClient) -> None:
        annotation = {
            "element_selector": "#x",
            "comment": "A very specific test instruction.",
            "page_url": PAGE_URL,
        }
        payload = {"page_url": PAGE_URL, "annotations": [annotation]}
        data = post_export(client, payload).get_json()
        assert "A very specific test instruction." in data["plain_text"]

    def test_http_url_accepted(self, client: FlaskClient) -> None:
        """http:// (non-TLS) URLs like local dev servers should be accepted."""
        annotation = {
            "element_selector": "#root",
            "comment": "Change colour.",
            "page_url": "http://localhost:3000",
        }
        payload = {"page_url": "http://localhost:3000", "annotations": [annotation]}
        response = post_export(client, payload)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /export – 400 client errors
# ---------------------------------------------------------------------------


class TestExportEndpointClientErrors:
    """Tests that POST /export returns 400 for malformed or invalid requests."""

    def test_non_json_content_type_returns_400(self, client: FlaskClient) -> None:
        response = post_export(client, "plain text body", content_type="text/plain")
        assert response.status_code == 400

    def test_non_json_content_type_error_message(self, client: FlaskClient) -> None:
        response = post_export(client, "plain text body", content_type="text/plain")
        data = response.get_json()
        assert "error" in data
        assert "Content-Type" in data["error"] or "JSON" in data["error"]

    def test_invalid_json_body_returns_400(self, client: FlaskClient) -> None:
        response = client.post(
            "/export",
            data="{not valid json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_json_array_body_returns_400(self, client: FlaskClient) -> None:
        """The root body must be an object, not an array."""
        response = post_export(client, [{"key": "val"}])
        assert response.status_code == 400

    def test_missing_page_url_returns_400(self, client: FlaskClient) -> None:
        payload = {"annotations": []}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_missing_page_url_error_message(self, client: FlaskClient) -> None:
        payload = {"annotations": []}
        data = post_export(client, payload).get_json()
        assert "page_url" in data["error"]

    def test_empty_page_url_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": "", "annotations": []}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_whitespace_page_url_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": "   ", "annotations": []}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_non_string_page_url_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": 12345, "annotations": []}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_missing_annotations_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_missing_annotations_error_message(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL}
        data = post_export(client, payload).get_json()
        assert "annotations" in data["error"]

    def test_non_list_annotations_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": "not a list"}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_annotation_item_not_object_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": ["string-not-object"]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_annotation_missing_selector_returns_400(self, client: FlaskClient) -> None:
        bad_annotation = {
            "comment": "ok",
            "page_url": PAGE_URL,
            # element_selector is missing
        }
        payload = {"page_url": PAGE_URL, "annotations": [bad_annotation]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_annotation_missing_comment_returns_400(self, client: FlaskClient) -> None:
        bad_annotation = {
            "element_selector": "#x",
            "page_url": PAGE_URL,
            # comment is missing
        }
        payload = {"page_url": PAGE_URL, "annotations": [bad_annotation]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_annotation_empty_selector_returns_400(self, client: FlaskClient) -> None:
        bad_annotation = {
            "element_selector": "",
            "comment": "ok",
            "page_url": PAGE_URL,
        }
        payload = {"page_url": PAGE_URL, "annotations": [bad_annotation]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_annotation_invalid_url_returns_400(self, client: FlaskClient) -> None:
        bad_annotation = {
            "element_selector": "#x",
            "comment": "ok",
            "page_url": "not-a-url",
        }
        payload = {"page_url": PAGE_URL, "annotations": [bad_annotation]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_error_response_contains_error_key(self, client: FlaskClient) -> None:
        """All 400 responses must include an 'error' key in the JSON body."""
        payload = {"page_url": "", "annotations": []}
        data = post_export(client, payload).get_json()
        assert "error" in data

    def test_error_response_content_type_is_json(self, client: FlaskClient) -> None:
        payload = {"page_url": "", "annotations": []}
        response = post_export(client, payload)
        assert response.content_type.startswith("application/json")

    def test_null_page_url_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": None, "annotations": []}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_integer_annotations_field_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": 42}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_annotation_integer_item_returns_400(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": [42]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_empty_comment_returns_400(self, client: FlaskClient) -> None:
        bad_annotation = {
            "element_selector": "#x",
            "comment": "",
            "page_url": PAGE_URL,
        }
        payload = {"page_url": PAGE_URL, "annotations": [bad_annotation]}
        response = post_export(client, payload)
        assert response.status_code == 400

    def test_whitespace_comment_returns_400(self, client: FlaskClient) -> None:
        bad_annotation = {
            "element_selector": "#x",
            "comment": "   ",
            "page_url": PAGE_URL,
        }
        payload = {"page_url": PAGE_URL, "annotations": [bad_annotation]}
        response = post_export(client, payload)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


class TestErrorHandlers:
    """Tests for the custom Flask error handlers."""

    def test_404_returns_json(self, client: FlaskClient) -> None:
        response = client.get("/nonexistent-route-xyz")
        assert response.status_code == 404
        assert response.content_type.startswith("application/json")

    def test_404_contains_error_key(self, client: FlaskClient) -> None:
        data = client.get("/nonexistent-route-xyz").get_json()
        assert "error" in data

    def test_405_returns_json(self, client: FlaskClient) -> None:
        # GET /export is not defined – only POST is
        response = client.get("/export")
        assert response.status_code == 405
        assert response.content_type.startswith("application/json")

    def test_405_contains_error_key(self, client: FlaskClient) -> None:
        data = client.get("/export").get_json()
        assert "error" in data

    def test_404_put_returns_json(self, client: FlaskClient) -> None:
        response = client.put("/does-not-exist")
        assert response.status_code == 404
        assert response.content_type.startswith("application/json")


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------


class TestCorsHeaders:
    """Tests that CORS headers are present so the extension popup can call the API."""

    def test_health_has_cors_header(self, client: FlaskClient) -> None:
        response = client.get("/health", headers={"Origin": "chrome-extension://abc123"})
        assert "Access-Control-Allow-Origin" in response.headers

    def test_export_has_cors_header(self, client: FlaskClient) -> None:
        payload = {"page_url": PAGE_URL, "annotations": []}
        response = client.post(
            "/export",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"Origin": "chrome-extension://abc123"},
        )
        assert "Access-Control-Allow-Origin" in response.headers

    def test_cors_allows_all_origins(self, client: FlaskClient) -> None:
        response = client.get("/health", headers={"Origin": "chrome-extension://abc123"})
        origin_header = response.headers.get("Access-Control-Allow-Origin", "")
        # flask-cors returns '*' or the echoed origin when credentials are not used
        assert origin_header in ("*", "chrome-extension://abc123")

    def test_cors_header_present_on_400(self, client: FlaskClient) -> None:
        """CORS headers should be present even on error responses."""
        payload = {"page_url": "", "annotations": []}
        response = client.post(
            "/export",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"Origin": "chrome-extension://testid"},
        )
        assert response.status_code == 400
        assert "Access-Control-Allow-Origin" in response.headers


# ---------------------------------------------------------------------------
# create_app factory
# ---------------------------------------------------------------------------


class TestCreateAppFactory:
    """Tests for the create_app factory function."""

    def test_returns_flask_instance(self) -> None:
        application = create_app()
        assert isinstance(application, Flask)

    def test_testing_flag_propagated(self) -> None:
        application = create_app({"TESTING": True})
        assert application.config["TESTING"] is True

    def test_two_instances_are_independent(self) -> None:
        app_a = create_app({"TESTING": True})
        app_b = create_app({"TESTING": True})
        assert app_a is not app_b

    def test_no_config_creates_app(self) -> None:
        application = create_app()
        assert application is not None

    def test_custom_config_key_set(self) -> None:
        application = create_app({"MY_CUSTOM_KEY": "hello"})
        assert application.config["MY_CUSTOM_KEY"] == "hello"


# ---------------------------------------------------------------------------
# Module-level app instance
# ---------------------------------------------------------------------------


class TestModuleLevelApp:
    """Tests that the module-level ``app`` instance is correctly exported."""

    def test_module_app_is_flask(self) -> None:
        from server.app import app as module_app

        assert isinstance(module_app, Flask)

    def test_module_app_has_health_route(self) -> None:
        from server.app import app as module_app

        client = module_app.test_client()
        response = client.get("/health")
        assert response.status_code == 200
