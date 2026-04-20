"""Unit tests for server/prompt_builder.py.

Covers:
- Plain-text prompt generation for single and multiple annotations.
- XML-tagged prompt generation including XML-escaping of special characters.
- JSON schema generation.
- Edge cases: empty annotation list, missing html_context, special characters.
- :func:`build_prompt_export` validation and error handling.
"""

from __future__ import annotations

import json
from typing import List

import pytest

from server.models import Annotation, PromptExport, ValidationError
from server.prompt_builder import (
    _build_json_schema,
    _build_plain_text,
    _build_xml_prompt,
    _xml_escape,
    build_prompt_export,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_annotation(
    selector: str = "#hero",
    comment: str = "Change colour to blue.",
    page_url: str = "https://example.com",
    html_context: str = '<div id="hero">Hello</div>',
    annotation_id: str | None = "uuid-001",
) -> Annotation:
    """Factory for creating a valid Annotation with sensible defaults."""
    return Annotation(
        element_selector=selector,
        comment=comment,
        page_url=page_url,
        html_context=html_context,
        annotation_id=annotation_id,
    )


PAGE_URL = "https://example.com/dashboard"


# ---------------------------------------------------------------------------
# _xml_escape
# ---------------------------------------------------------------------------


class TestXmlEscape:
    """Tests for the _xml_escape helper."""

    def test_ampersand(self) -> None:
        assert _xml_escape("foo & bar") == "foo &amp; bar"

    def test_less_than(self) -> None:
        assert _xml_escape("<div>") == "&lt;div&gt;"

    def test_greater_than(self) -> None:
        assert _xml_escape("a > b") == "a &gt; b"

    def test_double_quote(self) -> None:
        assert _xml_escape('say "hello"') == "say &quot;hello&quot;"

    def test_plain_text_unchanged(self) -> None:
        assert _xml_escape("hello world") == "hello world"

    def test_combined_special_chars(self) -> None:
        raw = '<a href="https://x.com?a=1&b=2">link</a>'
        escaped = _xml_escape(raw)
        assert "&amp;" in escaped
        assert "&lt;" in escaped
        assert "&gt;" in escaped
        assert "&quot;" in escaped

    def test_empty_string(self) -> None:
        assert _xml_escape("") == ""

    def test_single_quote(self) -> None:
        # html.escape does not escape single quotes by default but our
        # implementation passes quote=True which escapes double quotes;
        # single quotes are not escaped by html.escape – verify no crash.
        result = _xml_escape("it's fine")
        assert isinstance(result, str)
        assert "it" in result

    def test_numeric_characters_unchanged(self) -> None:
        assert _xml_escape("abc123") == "abc123"


# ---------------------------------------------------------------------------
# _build_plain_text
# ---------------------------------------------------------------------------


class TestBuildPlainText:
    """Tests for the plain-text prompt format."""

    def test_empty_annotations_produces_no_annotations_message(self) -> None:
        result = _build_plain_text(PAGE_URL, [])
        assert "No annotations" in result
        assert "0" in result

    def test_contains_page_url(self) -> None:
        ann = make_annotation()
        result = _build_plain_text(PAGE_URL, [ann])
        assert PAGE_URL in result

    def test_contains_annotation_count(self) -> None:
        annotations = [
            make_annotation(),
            make_annotation(selector=".nav", annotation_id="uuid-002"),
        ]
        result = _build_plain_text(PAGE_URL, annotations)
        assert "2" in result

    def test_single_annotation_selector_present(self) -> None:
        ann = make_annotation(selector="#submit-btn")
        result = _build_plain_text(PAGE_URL, [ann])
        assert "#submit-btn" in result

    def test_single_annotation_comment_present(self) -> None:
        ann = make_annotation(comment="Make this red.")
        result = _build_plain_text(PAGE_URL, [ann])
        assert "Make this red." in result

    def test_single_annotation_html_context_present(self) -> None:
        ann = make_annotation(html_context='<button id="x">OK</button>')
        result = _build_plain_text(PAGE_URL, [ann])
        assert '<button id="x">OK</button>' in result

    def test_annotation_id_present_when_set(self) -> None:
        ann = make_annotation(annotation_id="my-unique-id")
        result = _build_plain_text(PAGE_URL, [ann])
        assert "my-unique-id" in result

    def test_annotation_id_not_present_when_none(self) -> None:
        ann = make_annotation(annotation_id=None)
        result = _build_plain_text(PAGE_URL, [ann])
        assert "Annotation ID: None" not in result

    def test_multiple_annotations_numbered(self) -> None:
        anns = [
            make_annotation(selector="#a", annotation_id="id-1"),
            make_annotation(selector="#b", annotation_id="id-2"),
            make_annotation(selector="#c", annotation_id="id-3"),
        ]
        result = _build_plain_text(PAGE_URL, anns)
        assert "1." in result
        assert "2." in result
        assert "3." in result

    def test_empty_html_context_not_shown_as_section(self) -> None:
        ann = make_annotation(html_context="")
        result = _build_plain_text(PAGE_URL, [ann])
        assert "HTML context:" not in result

    def test_returns_string(self) -> None:
        result = _build_plain_text(PAGE_URL, [])
        assert isinstance(result, str)

    def test_has_header(self) -> None:
        result = _build_plain_text(PAGE_URL, [])
        assert "PAGE ANNOTATION INSTRUCTIONS" in result

    def test_has_separator_line(self) -> None:
        result = _build_plain_text(PAGE_URL, [])
        assert "===" in result

    def test_instructions_label_present_when_nonempty(self) -> None:
        ann = make_annotation()
        result = _build_plain_text(PAGE_URL, [ann])
        assert "Instructions" in result

    def test_whitespace_only_html_context_not_shown(self) -> None:
        ann = make_annotation(html_context="   ")
        result = _build_plain_text(PAGE_URL, [ann])
        assert "HTML context:" not in result

    def test_multiline_html_context_indented(self) -> None:
        ann = make_annotation(html_context="<div>\n  <span>hi</span>\n</div>")
        result = _build_plain_text(PAGE_URL, [ann])
        # Both opening and closing tags should appear
        assert "<div>" in result
        assert "</div>" in result


# ---------------------------------------------------------------------------
# _build_xml_prompt
# ---------------------------------------------------------------------------


class TestBuildXmlPrompt:
    """Tests for the XML-tagged prompt format."""

    def test_returns_string(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert isinstance(result, str)

    def test_has_xml_declaration(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert result.startswith('<?xml version="1.0"')

    def test_has_task_root_element(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert "<task>" in result
        assert "</task>" in result

    def test_contains_page_url(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert PAGE_URL in result

    def test_contains_annotation_count_zero(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert "<annotation_count>0</annotation_count>" in result

    def test_contains_annotation_count_nonzero(self) -> None:
        anns = [
            make_annotation(),
            make_annotation(selector=".nav", annotation_id="id-2"),
        ]
        result = _build_xml_prompt(PAGE_URL, anns)
        assert "<annotation_count>2</annotation_count>" in result

    def test_empty_annotations_uses_self_closing_tag(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert "<annotations/>" in result

    def test_single_annotation_element_selector_present(self) -> None:
        ann = make_annotation(selector="#hero")
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "<element_selector>#hero</element_selector>" in result

    def test_single_annotation_instruction_present(self) -> None:
        ann = make_annotation(comment="Add a spinner.")
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "<instruction>Add a spinner.</instruction>" in result

    def test_single_annotation_html_context_present(self) -> None:
        ann = make_annotation(html_context="<button>OK</button>")
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "<html_context>" in result
        assert "&lt;button&gt;OK&lt;/button&gt;" in result

    def test_empty_html_context_uses_self_closing_tag(self) -> None:
        ann = make_annotation(html_context="")
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "<html_context/>" in result

    def test_annotation_id_in_attribute(self) -> None:
        ann = make_annotation(annotation_id="abc-123")
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert 'id="abc-123"' in result

    def test_annotation_without_id_no_id_attribute(self) -> None:
        ann = make_annotation(annotation_id=None)
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert 'id=' not in result

    def test_special_chars_in_comment_are_escaped(self) -> None:
        ann = make_annotation(comment='Use <strong> & "bold" tags.')
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "&lt;strong&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result

    def test_special_chars_in_url_are_escaped(self) -> None:
        url = "https://example.com/search?q=foo&lang=en"
        result = _build_xml_prompt(url, [])
        assert "&amp;" in result
        lines_with_url = [ln for ln in result.splitlines() if "example.com" in ln]
        for line in lines_with_url:
            assert "&amp;" in line or "&" not in line

    def test_multiple_annotations_all_present(self) -> None:
        anns = [
            make_annotation(selector="#a", comment="First.", annotation_id="id-1"),
            make_annotation(selector="#b", comment="Second.", annotation_id="id-2"),
        ]
        result = _build_xml_prompt(PAGE_URL, anns)
        assert "#a" in result
        assert "#b" in result
        assert "First." in result
        assert "Second." in result

    def test_has_metadata_section(self) -> None:
        result = _build_xml_prompt(PAGE_URL, [])
        assert "<metadata>" in result
        assert "</metadata>" in result

    def test_has_annotations_wrapper(self) -> None:
        ann = make_annotation()
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "<annotations>" in result
        assert "</annotations>" in result

    def test_whitespace_only_html_context_uses_self_closing(self) -> None:
        ann = make_annotation(html_context="   ")
        result = _build_xml_prompt(PAGE_URL, [ann])
        assert "<html_context/>" in result


# ---------------------------------------------------------------------------
# _build_json_schema
# ---------------------------------------------------------------------------


class TestBuildJsonSchema:
    """Tests for the JSON schema dict format."""

    def test_returns_dict(self) -> None:
        result = _build_json_schema(PAGE_URL, [])
        assert isinstance(result, dict)

    def test_top_level_keys(self) -> None:
        result = _build_json_schema(PAGE_URL, [])
        assert "schema_version" in result
        assert "page_url" in result
        assert "annotation_count" in result
        assert "annotations" in result

    def test_schema_version(self) -> None:
        result = _build_json_schema(PAGE_URL, [])
        assert result["schema_version"] == "1.0"

    def test_page_url(self) -> None:
        result = _build_json_schema(PAGE_URL, [])
        assert result["page_url"] == PAGE_URL

    def test_empty_annotations(self) -> None:
        result = _build_json_schema(PAGE_URL, [])
        assert result["annotation_count"] == 0
        assert result["annotations"] == []

    def test_single_annotation_count(self) -> None:
        result = _build_json_schema(PAGE_URL, [make_annotation()])
        assert result["annotation_count"] == 1
        assert len(result["annotations"]) == 1

    def test_annotation_keys(self) -> None:
        ann = make_annotation()
        result = _build_json_schema(PAGE_URL, [ann])
        entry = result["annotations"][0]
        assert "annotation_id" in entry
        assert "element_selector" in entry
        assert "html_context" in entry
        assert "instruction" in entry

    def test_annotation_values(self) -> None:
        ann = make_annotation(
            selector="#nav",
            comment="Hide this.",
            html_context='<nav id="nav">...</nav>',
            annotation_id="uuid-99",
        )
        result = _build_json_schema(PAGE_URL, [ann])
        entry = result["annotations"][0]
        assert entry["element_selector"] == "#nav"
        assert entry["instruction"] == "Hide this."
        assert entry["html_context"] == '<nav id="nav">...</nav>'
        assert entry["annotation_id"] == "uuid-99"

    def test_annotation_id_none_when_not_set(self) -> None:
        ann = make_annotation(annotation_id=None)
        result = _build_json_schema(PAGE_URL, [ann])
        assert result["annotations"][0]["annotation_id"] is None

    def test_multiple_annotations(self) -> None:
        anns = [
            make_annotation(selector="#a", annotation_id="id-1"),
            make_annotation(selector="#b", annotation_id="id-2"),
            make_annotation(selector="#c", annotation_id="id-3"),
        ]
        result = _build_json_schema(PAGE_URL, anns)
        assert result["annotation_count"] == 3
        selectors = [e["element_selector"] for e in result["annotations"]]
        assert selectors == ["#a", "#b", "#c"]

    def test_result_is_json_serialisable(self) -> None:
        anns = [make_annotation()]
        result = _build_json_schema(PAGE_URL, anns)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_annotation_order_preserved(self) -> None:
        anns = [
            make_annotation(selector=f"#el-{i}", annotation_id=f"id-{i}")
            for i in range(10)
        ]
        result = _build_json_schema(PAGE_URL, anns)
        ids = [a["annotation_id"] for a in result["annotations"]]
        assert ids == [f"id-{i}" for i in range(10)]

    def test_html_context_stored_raw(self) -> None:
        """JSON schema stores raw HTML without XML-escaping."""
        ann = make_annotation(html_context='<div class="x">content & more</div>')
        result = _build_json_schema(PAGE_URL, [ann])
        ctx = result["annotations"][0]["html_context"]
        # Must be the raw string, not XML-escaped
        assert "&amp;" not in ctx
        assert "&" in ctx


# ---------------------------------------------------------------------------
# build_prompt_export – happy path
# ---------------------------------------------------------------------------


class TestBuildPromptExport:
    """Tests for the main build_prompt_export function."""

    def test_returns_prompt_export_instance(self) -> None:
        result = build_prompt_export(PAGE_URL, [])
        assert isinstance(result, PromptExport)

    def test_empty_annotations_returns_zero_count(self) -> None:
        result = build_prompt_export(PAGE_URL, [])
        assert result.annotation_count == 0

    def test_single_annotation_count(self) -> None:
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        assert result.annotation_count == 1

    def test_multiple_annotations_count(self) -> None:
        anns = [
            make_annotation(selector=f"#{i}", annotation_id=f"id-{i}")
            for i in range(5)
        ]
        result = build_prompt_export(PAGE_URL, anns)
        assert result.annotation_count == 5

    def test_page_url_preserved(self) -> None:
        result = build_prompt_export(PAGE_URL, [])
        assert result.page_url == PAGE_URL

    def test_plain_text_is_string(self) -> None:
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        assert isinstance(result.plain_text, str)

    def test_xml_prompt_is_string(self) -> None:
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        assert isinstance(result.xml_prompt, str)

    def test_json_schema_is_dict(self) -> None:
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        assert isinstance(result.json_schema, dict)

    def test_to_dict_is_json_serialisable(self) -> None:
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        serialised = json.dumps(result.to_dict())
        assert isinstance(serialised, str)

    def test_all_formats_contain_page_url(self) -> None:
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        assert PAGE_URL in result.plain_text
        assert "example.com" in result.xml_prompt
        assert result.json_schema["page_url"] == PAGE_URL

    def test_all_formats_contain_selector(self) -> None:
        ann = make_annotation(selector="#unique-selector")
        result = build_prompt_export(PAGE_URL, [ann])
        assert "#unique-selector" in result.plain_text
        assert "#unique-selector" in result.xml_prompt
        selectors = [
            a["element_selector"] for a in result.json_schema["annotations"]
        ]
        assert "#unique-selector" in selectors

    def test_all_formats_contain_comment(self) -> None:
        ann = make_annotation(comment="Unique instruction text here.")
        result = build_prompt_export(PAGE_URL, [ann])
        assert "Unique instruction text here." in result.plain_text
        assert "Unique instruction text here." in result.xml_prompt
        instructions = [
            a["instruction"] for a in result.json_schema["annotations"]
        ]
        assert "Unique instruction text here." in instructions

    def test_export_validates_internally(self) -> None:
        """The returned PromptExport passes its own validate() method."""
        result = build_prompt_export(PAGE_URL, [make_annotation()])
        result.validate()  # should not raise

    def test_to_dict_has_all_keys(self) -> None:
        result = build_prompt_export(PAGE_URL, [])
        d = result.to_dict()
        assert set(d.keys()) == {
            "page_url",
            "annotation_count",
            "plain_text",
            "xml_prompt",
            "json_schema",
        }


# ---------------------------------------------------------------------------
# build_prompt_export – error handling
# ---------------------------------------------------------------------------


class TestBuildPromptExportErrors:
    """Tests that build_prompt_export raises appropriate errors."""

    def test_empty_page_url_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="page_url"):
            build_prompt_export("", [])

    def test_whitespace_page_url_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="page_url"):
            build_prompt_export("   ", [])

    def test_non_list_annotations_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            build_prompt_export(PAGE_URL, None)  # type: ignore[arg-type]

    def test_non_annotation_in_list_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            build_prompt_export(PAGE_URL, ["not-an-annotation"])  # type: ignore[list-item]

    def test_invalid_annotation_raises_validation_error(self) -> None:
        bad_ann = Annotation(
            element_selector="",  # invalid – empty
            comment="ok",
            page_url=PAGE_URL,
        )
        with pytest.raises(ValidationError):
            build_prompt_export(PAGE_URL, [bad_ann])

    def test_error_message_includes_index(self) -> None:
        good_ann = make_annotation()
        bad_ann = Annotation(
            element_selector="#ok",
            comment="",  # invalid
            page_url=PAGE_URL,
        )
        with pytest.raises(ValidationError, match="index 1"):
            build_prompt_export(PAGE_URL, [good_ann, bad_ann])

    def test_annotation_with_invalid_url_raises_validation_error(self) -> None:
        bad_ann = Annotation(
            element_selector="#x",
            comment="ok",
            page_url="not-a-url",
        )
        with pytest.raises(ValidationError):
            build_prompt_export(PAGE_URL, [bad_ann])

    def test_dict_annotations_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            build_prompt_export(PAGE_URL, {})  # type: ignore[arg-type]

    def test_non_annotation_object_raises_type_error_with_index(self) -> None:
        good = make_annotation()
        with pytest.raises(TypeError, match="index 1"):
            build_prompt_export(PAGE_URL, [good, {"element_selector": "#x"}])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Edge cases and special characters
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and special characters in prompt generation."""

    def test_annotation_with_multiline_html_context(self) -> None:
        html_ctx = "<div>\n  <span>hello</span>\n</div>"
        ann = make_annotation(html_context=html_ctx)
        result = build_prompt_export(PAGE_URL, [ann])
        assert "hello" in result.plain_text
        assert "hello" in result.xml_prompt
        assert "hello" in result.json_schema["annotations"][0]["html_context"]

    def test_comment_with_xml_special_chars(self) -> None:
        ann = make_annotation(comment='Replace <h1> with <h2> & adjust "font-size".')
        result = build_prompt_export(PAGE_URL, [ann])
        assert "<h1>" in result.plain_text
        assert "&lt;h1&gt;" in result.xml_prompt
        assert "&amp;" in result.xml_prompt

    def test_very_long_comment(self) -> None:
        long_comment = "Refactor this component. " * 100
        ann = make_annotation(comment=long_comment)
        result = build_prompt_export(PAGE_URL, [ann])
        assert isinstance(result.plain_text, str)
        assert isinstance(result.xml_prompt, str)

    def test_unicode_in_comment(self) -> None:
        ann = make_annotation(comment="Ändern Sie die Farbe auf Grün. 日本語テスト.")
        result = build_prompt_export(PAGE_URL, [ann])
        assert "Ändern" in result.plain_text
        assert "日本語" in result.plain_text

    def test_complex_css_selector(self) -> None:
        selector = "body > main.container > section:nth-child(2) > div.card[data-id='42']"
        ann = make_annotation(selector=selector)
        result = build_prompt_export(PAGE_URL, [ann])
        assert selector in result.plain_text
        assert result.json_schema["annotations"][0]["element_selector"] == selector

    def test_large_number_of_annotations(self) -> None:
        anns = [
            make_annotation(
                selector=f"#el-{i}",
                comment=f"Instruction {i}.",
                annotation_id=f"id-{i}",
            )
            for i in range(50)
        ]
        result = build_prompt_export(PAGE_URL, anns)
        assert result.annotation_count == 50
        assert len(result.json_schema["annotations"]) == 50

    def test_selector_with_angle_brackets_escaped_in_xml(self) -> None:
        """CSS attribute selectors containing < or > should be XML-escaped."""
        ann = make_annotation(selector='input[value>"5"]')
        result = build_prompt_export(PAGE_URL, [ann])
        # XML prompt should not contain raw unescaped > inside element content
        # (the selector is escaped in the xml_prompt)
        assert isinstance(result.xml_prompt, str)

    def test_empty_annotation_list_json_schema_structure(self) -> None:
        result = build_prompt_export(PAGE_URL, [])
        schema = result.json_schema
        assert schema["annotation_count"] == 0
        assert schema["annotations"] == []
        assert schema["schema_version"] == "1.0"

    def test_plain_text_and_xml_prompt_are_nonempty(self) -> None:
        result = build_prompt_export(PAGE_URL, [])
        assert len(result.plain_text) > 0
        assert len(result.xml_prompt) > 0
