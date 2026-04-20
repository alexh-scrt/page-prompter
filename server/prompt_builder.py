"""Prompt builder for the page_prompter server.

Transforms one or more :class:`~server.models.Annotation` objects into three
structured prompt formats:

* **plain_text** – a numbered instruction list suitable for pasting into any
  AI chat interface.
* **xml_prompt** – an XML-tagged prompt structured for AI coding agents such
  as Claude or Cursor that understand hierarchical context tags.
* **json_schema** – a JSON-serialisable dictionary for programmatic
  consumption by other tools or agents.

The main entry-point is :func:`build_prompt_export`, which accepts a page URL
and a list of :class:`~server.models.Annotation` objects and returns a fully
populated :class:`~server.models.PromptExport` instance.

Example usage::

    from server.models import Annotation
    from server.prompt_builder import build_prompt_export

    annotations = [
        Annotation(
            element_selector="#submit-btn",
            comment="Change the button colour to green.",
            page_url="https://example.com/dashboard",
            html_context='<button id="submit-btn">Submit</button>',
            annotation_id="uuid-1234",
        )
    ]
    export = build_prompt_export("https://example.com/dashboard", annotations)
    print(export.plain_text)
    print(export.xml_prompt)
    print(export.json_schema)
"""

from __future__ import annotations

import html as html_module
import json
from typing import List, Optional

from server.models import Annotation, PromptExport, ValidationError


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_prompt_export(
    page_url: str,
    annotations: List[Annotation],
) -> PromptExport:
    """Build a :class:`~server.models.PromptExport` from a list of annotations.

    Validates every annotation before building any format so that callers
    receive a single, clear :class:`~server.models.ValidationError` if any
    annotation is malformed.

    Args:
        page_url: The URL of the annotated page.  Must be a non-empty string
            starting with ``http://`` or ``https://``.
        annotations: A list of :class:`~server.models.Annotation` objects to
            include in the export.  May be empty, in which case all output
            formats will indicate that no annotations are present.

    Returns:
        A fully populated :class:`~server.models.PromptExport` whose
        ``annotation_count`` equals ``len(annotations)``.

    Raises:
        ValidationError: If *page_url* is empty/blank, or if any annotation
            fails its own :meth:`~server.models.Annotation.validate` check.
        TypeError: If *annotations* is not a list.
    """
    if not isinstance(page_url, str) or not page_url.strip():
        raise ValidationError("'page_url' must be a non-empty string.")

    if not isinstance(annotations, list):
        raise TypeError(
            f"'annotations' must be a list, got {type(annotations).__name__!r}."
        )

    # Validate every annotation up-front so we fail fast with a useful message.
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, Annotation):
            raise TypeError(
                f"Item at index {index} is not an Annotation instance; "
                f"got {type(annotation).__name__!r}."
            )
        try:
            annotation.validate()
        except ValidationError as exc:
            raise ValidationError(
                f"Annotation at index {index} (id={annotation.annotation_id!r}) "
                f"is invalid: {exc}"
            ) from exc

    plain_text = _build_plain_text(page_url, annotations)
    xml_prompt = _build_xml_prompt(page_url, annotations)
    json_schema = _build_json_schema(page_url, annotations)

    export = PromptExport(
        page_url=page_url,
        plain_text=plain_text,
        xml_prompt=xml_prompt,
        json_schema=json_schema,
        annotation_count=len(annotations),
    )
    export.validate()
    return export


# ---------------------------------------------------------------------------
# Plain-text format
# ---------------------------------------------------------------------------


def _build_plain_text(page_url: str, annotations: List[Annotation]) -> str:
    """Build a plain-text numbered instruction list.

    The output is designed to be pasted directly into a chat window with any
    AI assistant.  It contains the page URL as a header followed by a numbered
    list of instructions, each including the CSS selector, any HTML context,
    and the developer's comment.

    Args:
        page_url: The URL of the annotated page.
        annotations: Validated list of annotations.

    Returns:
        A formatted multi-line string.
    """
    lines: List[str] = [
        "PAGE ANNOTATION INSTRUCTIONS",
        "============================",
        f"Page URL: {page_url}",
        f"Total annotations: {len(annotations)}",
        "",
    ]

    if not annotations:
        lines.append("(No annotations provided.)")
        return "\n".join(lines)

    lines.append("Instructions:")
    lines.append("")

    for index, ann in enumerate(annotations, start=1):
        lines.append(f"{index}. Element: {ann.element_selector}")
        if ann.annotation_id:
            lines.append(f"   Annotation ID: {ann.annotation_id}")
        if ann.html_context.strip():
            lines.append(f"   HTML context:")
            # Indent each line of the HTML context for readability
            for html_line in ann.html_context.splitlines():
                lines.append(f"     {html_line}")
        lines.append(f"   Instruction: {ann.comment}")
        lines.append("")

    # Remove trailing blank line
    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# XML-tagged format
# ---------------------------------------------------------------------------


def _build_xml_prompt(page_url: str, annotations: List[Annotation]) -> str:
    """Build an XML-tagged prompt for structured AI agent consumption.

    Produces a document with a ``<task>`` root element containing page metadata
    and one ``<annotation>`` element per annotation.  All user-supplied text is
    XML-escaped to prevent injection issues.

    Args:
        page_url: The URL of the annotated page.
        annotations: Validated list of annotations.

    Returns:
        A formatted XML string.
    """
    escaped_url = _xml_escape(page_url)
    count = len(annotations)

    xml_lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<task>",
        "  <metadata>",
        f"    <page_url>{escaped_url}</page_url>",
        f"    <annotation_count>{count}</annotation_count>",
        "  </metadata>",
    ]

    if not annotations:
        xml_lines.append("  <annotations/>")
    else:
        xml_lines.append("  <annotations>")
        for ann in annotations:
            xml_lines.extend(_annotation_to_xml_lines(ann, indent=4))
        xml_lines.append("  </annotations>")

    xml_lines.append("</task>")
    return "\n".join(xml_lines)


def _annotation_to_xml_lines(ann: Annotation, indent: int = 4) -> List[str]:
    """Render a single annotation as XML lines.

    Args:
        ann: The annotation to render.
        indent: Number of leading spaces for the top-level element.

    Returns:
        A list of strings (one per XML line) without a trailing newline.
    """
    pad = " " * indent
    inner_pad = " " * (indent + 2)

    id_attr = ""
    if ann.annotation_id:
        id_attr = f' id="{_xml_escape(ann.annotation_id)}"'

    lines: List[str] = [f"{pad}<annotation{id_attr}>"]

    lines.append(
        f"{inner_pad}<element_selector>{_xml_escape(ann.element_selector)}"
        f"</element_selector>"
    )

    if ann.html_context.strip():
        lines.append(
            f"{inner_pad}<html_context>"
            f"{_xml_escape(ann.html_context)}"
            f"</html_context>"
        )
    else:
        lines.append(f"{inner_pad}<html_context/>")

    lines.append(
        f"{inner_pad}<instruction>{_xml_escape(ann.comment)}</instruction>"
    )

    lines.append(f"{pad}</annotation>")
    return lines


def _xml_escape(text: str) -> str:
    """Escape special XML characters in *text*.

    Uses :func:`html.escape` which handles ``&``, ``<``, ``>``, ``\'``, and
    ``\"`` correctly.  The ``quote=True`` argument ensures double-quotes are
    also escaped, which is needed for attribute values.

    Args:
        text: Raw string that may contain XML special characters.

    Returns:
        An XML-safe string.
    """
    return html_module.escape(text, quote=True)


# ---------------------------------------------------------------------------
# JSON schema format
# ---------------------------------------------------------------------------


def _build_json_schema(
    page_url: str,
    annotations: List[Annotation],
) -> dict:
    """Build a JSON-serialisable dictionary representing the annotations.

    The structure is designed to be consumed programmatically by other tools,
    scripts, or AI agents that prefer structured data over prose.

    Schema::

        {
            "schema_version": "1.0",
            "page_url": "<url>",
            "annotation_count": <int>,
            "annotations": [
                {
                    "annotation_id": "<str | null>",
                    "element_selector": "<css selector>",
                    "html_context": "<html snippet>",
                    "instruction": "<developer comment>"
                },
                ...
            ]
        }

    Args:
        page_url: The URL of the annotated page.
        annotations: Validated list of annotations.

    Returns:
        A plain dictionary that is safe to pass to ``json.dumps``.
    """
    annotation_dicts = [
        {
            "annotation_id": ann.annotation_id,
            "element_selector": ann.element_selector,
            "html_context": ann.html_context,
            "instruction": ann.comment,
        }
        for ann in annotations
    ]

    return {
        "schema_version": "1.0",
        "page_url": page_url,
        "annotation_count": len(annotations),
        "annotations": annotation_dicts,
    }
