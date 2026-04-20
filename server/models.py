"""Data models for the page_prompter server.

Defines the Annotation and PromptExport dataclasses used throughout the server
to represent user-created annotations and the structured prompt exports derived
from them.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Annotation:
    """Represents a single user annotation attached to a DOM element.

    Attributes:
        element_selector: CSS selector string that uniquely identifies the
            annotated DOM element on the page.
        comment: The developer's instruction or description of the desired
            change for this element.
        page_url: The full URL of the page where this annotation was created.
        html_context: A snippet of the surrounding HTML for additional context.
            Defaults to an empty string if not provided.
        annotation_id: An optional unique identifier for the annotation.
            Typically a UUID string assigned by the extension.
    """

    element_selector: str
    comment: str
    page_url: str
    html_context: str = field(default="")
    annotation_id: Optional[str] = field(default=None)


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
    """

    page_url: str
    plain_text: str
    xml_prompt: str
    json_schema: dict
    annotation_count: int
