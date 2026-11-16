"""Formatting template: defaults, YAML merge, and a documented sample file.

All lengths are in points unless the key name says otherwise. The template only
covers the generic baseline; schools with their own template can override every
value here.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


class TemplateError(ValueError):
    """Raised when a template file is malformed or contains unknown keys."""


@dataclass(frozen=True)
class Template:
    """Page geometry and typography values."""

    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    margin_top_cm: float = 2.54
    margin_bottom_cm: float = 2.54
    margin_left_cm: float = 3.0
    margin_right_cm: float = 2.5
    body_font_cn: str = "宋体"  # SimSun
    body_font_en: str = "Times New Roman"
    body_size_pt: float = 12.0
    line_spacing: float = 1.5
    first_line_indent_chars: float = 2.0
    heading_font: str = "黑体"  # SimHei
    heading_size_h1_pt: float = 18.0
    heading_size_h2_pt: float = 15.0
    heading_size_h3_pt: float = 13.0
    heading_space_before_pt: float = 12.0
    heading_space_after_pt: float = 6.0
    caption_size_pt: float = 10.5
    table_rule_pt: float = 1.5
    table_header_rule_pt: float = 0.75
    header_text_size_pt: float = 9.0
    page_number_size_pt: float = 10.5

    def as_dict(self) -> dict[str, float | str]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


_NUMERIC_FIELDS = {
    item.name
    for item in fields(Template)
    if isinstance(getattr(Template(), item.name), float)
}


def load(path: Path) -> Template:
    """Load a YAML template, merged over the built-in defaults."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise TemplateError(f"cannot read template {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TemplateError(f"template {path} is not valid YAML: {exc}") from exc
    return from_mapping(raw, source=str(path))


def from_mapping(raw: object, source: str = "template") -> Template:
    """Validate a mapping and return a Template."""
    if not isinstance(raw, dict):
        raise TemplateError(f"{source} must be a YAML mapping")
    known = set(Template().as_dict())
    unknown = sorted(set(raw) - known)
    if unknown:
        raise TemplateError(f"{source} has unknown key(s): {', '.join(unknown)}")
    values = Template().as_dict()
    for key, value in raw.items():
        if key in _NUMERIC_FIELDS:
            try:
                values[key] = float(value)
            except (TypeError, ValueError) as exc:
                raise TemplateError(f"{source}.{key} must be a number, got {value!r}") from exc
        else:
            values[key] = str(value)
    template = Template(**values)  # type: ignore[arg-type]
    if template.body_size_pt <= 0 or template.line_spacing <= 0:
        raise TemplateError(f"{source}: sizes and line spacing must be positive")
    usable_width = template.page_width_cm - template.margin_left_cm - template.margin_right_cm
    if usable_width <= 0:
        raise TemplateError(f"{source}: margins leave no usable page width")
    return template


SAMPLE_TEMPLATE = """\
# thesis-forge format template.
# Values are a generic baseline; check your school's rules before submitting.
page_width_cm: 21.0
page_height_cm: 29.7
margin_top_cm: 2.54
margin_bottom_cm: 2.54
margin_left_cm: 3.0
margin_right_cm: 2.5
body_font_cn: "宋体"
body_font_en: Times New Roman
body_size_pt: 12.0
line_spacing: 1.5
first_line_indent_chars: 2.0
heading_font: "黑体"
heading_size_h1_pt: 18.0
heading_size_h2_pt: 15.0
heading_size_h3_pt: 13.0
heading_space_before_pt: 12.0
heading_space_after_pt: 6.0
caption_size_pt: 10.5
table_rule_pt: 1.5
table_header_rule_pt: 0.75
header_text_size_pt: 9.0
page_number_size_pt: 10.5
"""
