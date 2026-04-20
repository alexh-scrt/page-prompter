"""Unit tests for server/models.py.

Covers construction, validation, serialisation, and round-trip behaviour for
both :class:`Annotation` and :class:`PromptExport`.
"""

import pytest

from server.models import Annotation, PromptExport, ValidationError


# ---------------------------------------------------------------------------
# Annotation – construction and happy-path validation
# ---------------------------------------------------------------------------

class TestAnnotationConstruction:
    """Tests for constructing valid Annotation objects."""

    def test_minimal_construction(self) -> None:
        """Annotation can be created with only the three required fields."""
        ann = Annotation(
            element_selector="#hero",
            comment="Make this red.",
            page_url="https://example.com",
        )
        assert ann.element_selector == "#hero"
        assert ann.comment == "Make this red."
        assert ann.page_url == "https://example.com"
        assert ann.html_context == ""
        assert ann.annotation_id is None

    def test_full_construction(self) -> None:
        """Annotation accepts all optional fields."""
        ann = Annotation(
            element_selector=".nav > li:first-child",
            comment="Remove this list item.",
            page_url="https://example.com/about",
            html_context="<li class=\"active\">Home</li>",
            annotation_id="uuid-abc-123",
        )
        assert ann.annotation_id == "uuid-abc-123"
        assert ann.html_context == "<li class=\"active\">Home</li>"

    def test_validate_passes_for_valid_annotation(self) -> None:
        """validate() does not raise for a fully valid Annotation."""
        ann = Annotation(
            element_selector="button.submit",
            comment="Add a loading spinner.",
            page_url="http://localhost:3000/dashboard",
            html_context="<button class=\"submit\">Submit</button>",
            annotation_id="deadbeef",
        )
        ann.validate()  # Should not raise

    def test_validate_accepts_http_url(self) -> None:
        """validate() accepts plain http:// URLs (for local dev servers)."""
        ann = Annotation(
            element_selector="#root",
            comment="Change font size.",
            page_url="http://localhost:8080",
        )
        ann.validate()

    def test_validate_accepts_https_url(self) -> None:
        """validate() accepts https:// URLs."""
        ann = Annotation(
            element_selector="#root",
            comment="Change font size.",
            page_url="https://my-app.example.com/page",
        )
        ann.validate()


# ---------------------------------------------------------------------------
# Annotation – validation failures
# ---------------------------------------------------------------------------

class TestAnnotationValidationErrors:
    """Tests that ValidationError is raised for invalid Annotation fields."""

    def test_empty_element_selector_raises(self) -> None:
        ann = Annotation(element_selector="   ", comment="ok", page_url="https://x.com")
        with pytest.raises(ValidationError, match="element_selector"):
            ann.validate()

    def test_empty_comment_raises(self) -> None:
        ann = Annotation(element_selector="#x", comment="", page_url="https://x.com")
        with pytest.raises(ValidationError, match="comment"):
            ann.validate()

    def test_whitespace_only_comment_raises(self) -> None:
        ann = Annotation(element_selector="#x", comment="   ", page_url="https://x.com")
        with pytest.raises(ValidationError, match="comment"):
            ann.validate()

    def test_empty_page_url_raises(self) -> None:
        ann = Annotation(element_selector="#x", comment="ok", page_url="")
        with pytest.raises(ValidationError, match="page_url"):
            ann.validate()

    def test_invalid_url_scheme_raises(self) -> None:
        ann = Annotation(element_selector="#x", comment="ok", page_url="ftp://example.com")
        with pytest.raises(ValidationError, match="page_url"):
            ann.validate()

    def test_relative_url_raises(self) -> None:
        ann = Annotation(element_selector="#x", comment="ok", page_url="/relative/path")
        with pytest.raises(ValidationError, match="page_url"):
            ann.validate()

    def test_non_string_annotation_id_raises(self) -> None:
        ann = Annotation(
            element_selector="#x",
            comment="ok",
            page_url="https://x.com",
            annotation_id=42,  # type: ignore[arg-type]
        )
        with pytest.raises(ValidationError, match="annotation_id"):
            ann.validate()

    def test_non_string_html_context_raises(self) -> None:
        ann = Annotation(
            element_selector="#x",
            comment="ok",
            page_url="https://x.com",
            html_context=123,  # type: ignore[arg-type]
        )
        with pytest.raises(ValidationError, match="html_context"):
            ann.validate()


# ---------------------------------------------------------------------------
# Annotation – serialisation round-trip
# ---------------------------------------------------------------------------

class TestAnnotationSerialisation:
    """Tests for to_dict() and from_dict() on Annotation."""

    def _make_annotation(self) -> Annotation:
        return Annotation(
            element_selector="#hero-title",
            comment="Increase font size to 48px.",
            page_url="https://example.com",
            html_context="<h1 id=\"hero-title\">Hello</h1>",
            annotation_id="test-uuid",
        )

    def test_to_dict_keys(self) -> None:
        d = self._make_annotation().to_dict()
        assert set(d.keys()) == {
            "annotation_id",
            "element_selector",
            "comment",
            "page_url",
            "html_context",
        }

    def test_to_dict_values(self) -> None:
        d = self._make_annotation().to_dict()
        assert d["element_selector"] == "#hero-title"
        assert d["comment"] == "Increase font size to 48px."
        assert d["page_url"] == "https://example.com"
        assert d["annotation_id"] == "test-uuid"
        assert d["html_context"] == "<h1 id=\"hero-title\">Hello</h1>"

    def test_round_trip(self) -> None:
        original = self._make_annotation()
        restored = Annotation.from_dict(original.to_dict())
        assert restored.element_selector == original.element_selector
        assert restored.comment == original.comment
        assert restored.page_url == original.page_url
        assert restored.html_context == original.html_context
        assert restored.annotation_id == original.annotation_id

    def test_from_dict_minimal(self) -> None:
        """from_dict() works with only the required keys."""
        data = {
            "element_selector": "h2",
            "comment": "Make bold.",
            "page_url": "https://example.com",
        }
        ann = Annotation.from_dict(data)
        assert ann.html_context == ""
        assert ann.annotation_id is None

    def test_from_dict_extra_keys_ignored(self) -> None:
        """from_dict() silently ignores unknown keys."""
        data = {
            "element_selector": "h2",
            "comment": "Make bold.",
            "page_url": "https://example.com",
            "unknown_key": "should be ignored",
        }
        ann = Annotation.from_dict(data)  # Should not raise
        assert ann.comment == "Make bold."

    def test_from_dict_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError, match="comment"):
            Annotation.from_dict({
                "element_selector": "#x",
                "page_url": "https://example.com",
            })

    def test_from_dict_validates_url(self) -> None:
        with pytest.raises(ValidationError, match="page_url"):
            Annotation.from_dict({
                "element_selector": "#x",
                "comment": "ok",
                "page_url": "not-a-url",
            })


# ---------------------------------------------------------------------------
# PromptExport – construction and happy-path validation
# ---------------------------------------------------------------------------

class TestPromptExportConstruction:
    """Tests for constructing valid PromptExport objects."""

    def _make_export(self, annotation_count: int = 1) -> PromptExport:
        return PromptExport(
            page_url="https://example.com",
            plain_text="1. Change the button colour to green.",
            xml_prompt="<task><instruction>Change colour</instruction></task>",
            json_schema={
                "page_url": "https://example.com",
                "annotations": [],
            },
            annotation_count=annotation_count,
        )

    def test_construction(self) -> None:
        export = self._make_export()
        assert export.page_url == "https://example.com"
        assert export.annotation_count == 1

    def test_validate_passes(self) -> None:
        self._make_export().validate()  # Should not raise

    def test_validate_zero_annotation_count_passes(self) -> None:
        """Zero is a valid annotation_count (empty export is allowed)."""
        self._make_export(annotation_count=0).validate()


# ---------------------------------------------------------------------------
# PromptExport – validation failures
# ---------------------------------------------------------------------------

class TestPromptExportValidationErrors:
    """Tests that ValidationError is raised for invalid PromptExport fields."""

    def _base(self, **overrides: object) -> PromptExport:
        defaults: dict = {
            "page_url": "https://example.com",
            "plain_text": "some text",
            "xml_prompt": "<x/>",
            "json_schema": {},
            "annotation_count": 1,
        }
        defaults.update(overrides)
        return PromptExport(**defaults)  # type: ignore[arg-type]

    def test_empty_page_url_raises(self) -> None:
        with pytest.raises(ValidationError, match="page_url"):
            self._base(page_url="").validate()

    def test_non_string_plain_text_raises(self) -> None:
        with pytest.raises(ValidationError, match="plain_text"):
            self._base(plain_text=None).validate()

    def test_non_string_xml_prompt_raises(self) -> None:
        with pytest.raises(ValidationError, match="xml_prompt"):
            self._base(xml_prompt=42).validate()

    def test_non_dict_json_schema_raises(self) -> None:
        with pytest.raises(ValidationError, match="json_schema"):
            self._base(json_schema=["list", "not", "dict"]).validate()

    def test_negative_annotation_count_raises(self) -> None:
        with pytest.raises(ValidationError, match="annotation_count"):
            self._base(annotation_count=-1).validate()

    def test_float_annotation_count_raises(self) -> None:
        with pytest.raises(ValidationError, match="annotation_count"):
            self._base(annotation_count=1.5).validate()


# ---------------------------------------------------------------------------
# PromptExport – serialisation
# ---------------------------------------------------------------------------

class TestPromptExportSerialisation:
    """Tests for to_dict() on PromptExport."""

    def test_to_dict_keys(self) -> None:
        export = PromptExport(
            page_url="https://example.com",
            plain_text="plain",
            xml_prompt="<xml/>",
            json_schema={"key": "value"},
            annotation_count=3,
        )
        d = export.to_dict()
        assert set(d.keys()) == {
            "page_url",
            "annotation_count",
            "plain_text",
            "xml_prompt",
            "json_schema",
        }

    def test_to_dict_values(self) -> None:
        export = PromptExport(
            page_url="https://example.com",
            plain_text="plain",
            xml_prompt="<xml/>",
            json_schema={"key": "value"},
            annotation_count=3,
        )
        d = export.to_dict()
        assert d["page_url"] == "https://example.com"
        assert d["annotation_count"] == 3
        assert d["plain_text"] == "plain"
        assert d["xml_prompt"] == "<xml/>"
        assert d["json_schema"] == {"key": "value"}
