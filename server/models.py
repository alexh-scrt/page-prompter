"""Data models for the page_prompter server.

Defines the Annotation and PromptExport dataclasses used throughout the server
to represent user-created annotations and the structured prompt exports derived
from them. Includes basic validation logic to ensure data integrity before
prompt generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import re


class ValidationError(ValueError):
    """Raised when an Annotation or PromptExport fails validation."""


@dataclass
class Annotation:
    """Represents a single user annotation attached to a DOM element.

    Attributes:
        element_selector: CSS selector string that uniquely identifies the
            annotated DOM element on the page.  Must be a non-empty string.
        comment: The developer's instruction or description of the desired
            change for this element.  Must be a non-empty string.
        page_url: The full URL of the page where this annotation was created.
            Must start with ``http://`` or ``https://``.
        html_context: A snippet of the surrounding HTML for additional context.
            Defaults to an empty string if not provided.
        annotation_id: An optional unique identifier for the annotation.
            Typically a UUID string assigned by the extension.

    Raises:
        ValidationError: If any required field is invalid when
            :meth:`validate` is called.

    Example::

        annotation = Annotation(
            element_selector="#submit-btn",
            comment="Change button colour to green.",
            page_url="https://example.com/dashboard",
            html_context='<button id="submit-btn">Submit</button>',
            annotation_id="uuid-1234",
        )
        annotation.validate()
    """

    element_selector: str
    comment: str
    page_url: str
    html_context: str = field(default="")
    annotation_id: Optional[str] = field(default=None)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validate the annotation fields.

        Checks that required string fields are non-empty after stripping
        whitespace and that *page_url* looks like a well-formed HTTP/HTTPS URL.

        Raises:
            ValidationError: Describing which field is invalid and why.
        """
        if not isinstance(self.element_selector, str) or not self.element_selector.strip():
            raise ValidationError(
                "'element_selector' must be a non-empty string."
            )

        if not isinstance(self.comment, str) or not self.comment.strip():
            raise ValidationError(
                "'comment' must be a non-empty string."
            )

        if not isinstance(self.page_url, str) or not self.page_url.strip():
            raise ValidationError(
                "'page_url' must be a non-empty string."
            )

        _url_pattern = re.compile(
            r"^https?://"           # scheme
            r"[^\s/$.?#]"          # first character of host
            r"[^\s]*$",            # rest of the URL
            re.IGNORECASE,
        )
        if not _url_pattern.match(self.page_url.strip()):
            raise ValidationError(
                f"'page_url' does not look like a valid HTTP/HTTPS URL: "
                f"{self.page_url!r}"
            )

        if self.annotation_id is not None and not isinstance(self.annotation_id, str):
            raise ValidationError(
                "'annotation_id' must be a string or None."
            )

        if not isinstance(self.html_context, str):
            raise ValidationError(
                "'html_context' must be a string."
            )

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the annotation to a plain dictionary.

        Returns:
            A dictionary representation suitable for JSON serialisation.
        """
        return {
            "annotation_id": self.annotation_id,
            "element_selector": self.element_selector,
            "comment": self.comment,
            "page_url": self.page_url,
            "html_context": self.html_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Annotation":
        """Construct an :class:`Annotation` from a plain dictionary.

        All keys except ``html_context`` and ``annotation_id`` are required.

        Args:
            data: Dictionary containing annotation fields.  Extra keys are
                silently ignored.

        Returns:
            A new :class:`Annotation` instance.

        Raises:
            ValidationError: If required keys are missing from *data*.
        """
        missing = {"element_selector", "comment", "page_url"} - set(data.keys())
        if missing:
            raise ValidationError(
                f"Missing required field(s) for Annotation: {', '.join(sorted(missing))}"
            )

        instance = cls(
            element_selector=data["element_selector"],
            comment=data["comment"],
            page_url=data["page_url"],
            html_context=data.get("html_context", ""),
            annotation_id=data.get("annotation_id"),
        )
        instance.validate()
        return instance


@dataclass
class PromptExport:
    """Represents the structured prompt output derived from one or more annotations.

    Attributes:
        page_url: The URL of the annotated page.
        plain_text: A plain-text formatted instruction list suitable for pasting
            directly into a chat with an AI assistant.
        xml_prompt: An XML-tagged prompt formatted for AI coding agents such as
            Claude or Cursor that understand structured XML context.
        json_schema: A JSON-serialisable dictionary representing the annotations
            and their context for programmatic consumption.
        annotation_count: The number of annotations included in this export.
            Must be a positive integer.

    Raises:
        ValidationError: If any field is invalid when :meth:`validate` is
            called.

    Example::

        export = PromptExport(
            page_url="https://example.com",
            plain_text="1. Change ...",
            xml_prompt="<task>...</task>",
            json_schema={"page_url": "https://example.com", "annotations": []},
            annotation_count=1,
        )
        export.validate()
    """

    page_url: str
    plain_text: str
    xml_prompt: str
    json_schema: dict
    annotation_count: int

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validate the prompt export fields.

        Raises:
            ValidationError: Describing which field is invalid and why.
        """
        if not isinstance(self.page_url, str) or not self.page_url.strip():
            raise ValidationError(
                "'page_url' must be a non-empty string."
            )

        if not isinstance(self.plain_text, str):
            raise ValidationError(
                "'plain_text' must be a string."
            )

        if not isinstance(self.xml_prompt, str):
            raise ValidationError(
                "'xml_prompt' must be a string."
            )

        if not isinstance(self.json_schema, dict):
            raise ValidationError(
                "'json_schema' must be a dictionary."
            )

        if not isinstance(self.annotation_count, int) or self.annotation_count < 0:
            raise ValidationError(
                "'annotation_count' must be a non-negative integer."
            )

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the prompt export to a plain dictionary.

        Returns:
            A dictionary representation suitable for JSON serialisation via
            Flask's ``jsonify`` or the standard ``json`` module.
        """
        return {
            "page_url": self.page_url,
            "annotation_count": self.annotation_count,
            "plain_text": self.plain_text,
            "xml_prompt": self.xml_prompt,
            "json_schema": self.json_schema,
        }
