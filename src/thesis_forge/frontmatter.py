"""Parse and validate the YAML front matter block of a thesis Markdown file.

Only the first fenced block of the document is treated as front matter. The
parser is deliberately strict: a thesis with no title or author is almost never
what the user wanted, so failing early beats producing a cover page full of
blanks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls

import yaml

FRONT_MATTER_DELIMITER = "---"
REQUIRED_FIELDS = ("title", "author", "institution")
OPTIONAL_FIELDS = ("major", "advisor", "date", "header_text")


class FrontMatterError(ValueError):
    """Raised when front matter is missing, malformed, or incomplete."""


@dataclass(frozen=True)
class FrontMatter:
    """Validated metadata used to build the cover page and document properties."""

    title: str
    author: str
    institution: str
    major: str = ""
    advisor: str = ""
    date: str = ""
    header_text: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def header(self) -> str:
        """Header text, falling back to the title when none is configured."""
        return self.header_text.strip() or self.title.strip()

    @property
    def parsed_date(self) -> date_cls:
        """Publication date as a date object (today when unset)."""
        if not self.date:
            return date_cls.today()
        try:
            return date_cls.fromisoformat(self.date)
        except ValueError as exc:
            raise FrontMatterError(
                f"date must be ISO 8601 (YYYY-MM-DD), got {self.date!r}"
            ) from exc


def split_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Split raw Markdown into (metadata mapping, body).

    The front matter must start on the first non-blank line and be closed by a
    second ``---`` line. A file without front matter gets an empty mapping.
    """
    lines = text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip() != FRONT_MATTER_DELIMITER:
        return {}, text

    for end in range(start + 1, len(lines)):
        if lines[end].strip() == FRONT_MATTER_DELIMITER:
            block = "\n".join(lines[start + 1 : end])
            body = "\n".join(lines[end + 1 :])
            try:
                data = yaml.safe_load(block) or {}
            except yaml.YAMLError as exc:
                raise FrontMatterError(f"front matter is not valid YAML: {exc}") from exc
            if not isinstance(data, dict):
                raise FrontMatterError("front matter must be a YAML mapping")
            return data, body
    raise FrontMatterError("front matter is not closed by a second '---' line")


def parse(text: str) -> tuple[FrontMatter, str]:
    """Return validated front matter and the Markdown body."""
    data, body = split_front_matter(text)
    if not data:
        raise FrontMatterError(
            "missing front matter: start the file with '---' and a YAML mapping"
        )

    missing = [name for name in REQUIRED_FIELDS if not str(data.get(name, "")).strip()]
    if missing:
        raise FrontMatterError(f"front matter is missing required field(s): {', '.join(missing)}")

    unknown = sorted(set(data) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    values = {name: str(data.get(name, "") or "").strip() for name in OPTIONAL_FIELDS}
    front = FrontMatter(
        title=str(data["title"]).strip(),
        author=str(data["author"]).strip(),
        institution=str(data["institution"]).strip(),
        major=values["major"],
        advisor=values["advisor"],
        date=values["date"],
        header_text=values["header_text"],
        extra={name: str(data[name]) for name in unknown},
    )
    _ = front.parsed_date  # validate eagerly
    return front, body
