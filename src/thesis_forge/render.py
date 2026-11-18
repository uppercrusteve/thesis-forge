"""Render Markdown thesis sources into a .docx with a generic university layout.

The renderer walks the markdown-it token stream. It intentionally supports a
small, predictable Markdown subset: headings, paragraphs, lists, block quotes,
fenced code, pipe tables, images, emphasis, and inline code. Anything else is
rendered as plain text rather than silently dropped.

Numbering of figures and tables is automatic. A line ``表: caption`` directly
before a pipe table supplies the table caption; image alt text supplies the
figure caption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.exceptions import UnrecognizedImageError
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from markdown_it import MarkdownIt

from . import __version__
from .frontmatter import FrontMatter
from .frontmatter import parse as parse_front_matter
from .template import Template

CAPTION_PREFIX = re.compile(r"^表\s*[:：]\s*(.*)$")
REFERENCE_HEADINGS = {"参考文献", "references", "bibliography"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf"}


@dataclass
class BuildResult:
    """Outcome of a build, including non-fatal warnings."""

    path: Path
    warnings: list[str] = field(default_factory=list)
    figure_count: int = 0
    table_count: int = 0


def _set_rfonts(rpr, ascii_name: str, east_name: str) -> None:
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), ascii_name)
    fonts.set(qn("w:hAnsi"), ascii_name)
    fonts.set(qn("w:eastAsia"), east_name)
    fonts.set(qn("w:cs"), ascii_name)


def _run_fonts(run, ascii_name: str, east_name: str, size_pt: float, bold: bool = False) -> None:
    run.font.name = ascii_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold or None
    _set_rfonts(run._r.get_or_add_rPr(), ascii_name, east_name)


def _add_field(paragraph, instruction: str, placeholder: str = "") -> None:
    """Insert a complex field (begin/instr/separate/result/end)."""
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin_run._r.append(begin)

    instr_run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    instr_run._r.append(instr)

    sep_run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    sep_run._r.append(separate)

    if placeholder:
        paragraph.add_run(placeholder)

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run._r.append(end)


def _set_page_geometry(section, template: Template) -> None:
    section.page_width = Cm(template.page_width_cm)
    section.page_height = Cm(template.page_height_cm)
    section.top_margin = Cm(template.margin_top_cm)
    section.bottom_margin = Cm(template.margin_bottom_cm)
    section.left_margin = Cm(template.margin_left_cm)
    section.right_margin = Cm(template.margin_right_cm)
    section.header_distance = Cm(1.5)
    section.footer_distance = Cm(1.5)


def _patch_styles(document, template: Template) -> None:
    normal = document.styles["Normal"]
    normal.font.name = template.body_font_en
    normal.font.size = Pt(template.body_size_pt)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    _set_rfonts(normal.element.get_or_add_rPr(), template.body_font_en, template.body_font_cn)

    paragraph = normal.paragraph_format
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.line_spacing = template.line_spacing
    paragraph.space_before = Pt(0)
    paragraph.space_after = Pt(0)
    ind = normal.element.get_or_add_pPr().get_or_add_ind()
    ind.set(qn("w:firstLineChars"), str(int(round(template.first_line_indent_chars * 100))))
    ind.set(
        qn("w:firstLine"),
        str(int(round(template.first_line_indent_chars * template.body_size_pt * 20))),
    )

    sizes = {
        1: template.heading_size_h1_pt,
        2: template.heading_size_h2_pt,
        3: template.heading_size_h3_pt,
    }
    for level, size in sizes.items():
        style = document.styles[f"Heading {level}"]
        style.font.name = template.heading_font
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.italic = False
        style.font.color.rgb = RGBColor(0, 0, 0)
        _set_rfonts(style.element.get_or_add_rPr(), template.heading_font, template.heading_font)
        fmt = style.paragraph_format
        fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fmt.first_line_indent = Pt(0)
        fmt.space_before = Pt(template.heading_space_before_pt)
        fmt.space_after = Pt(template.heading_space_after_pt)
        fmt.line_spacing = template.line_spacing
        fmt.keep_with_next = True
        if level == 1:
            fmt.page_break_before = True
        ppr = style.element.get_or_add_pPr()
        for old in ppr.findall(qn("w:outlineLvl")):
            ppr.remove(old)
        outline = OxmlElement("w:outlineLvl")
        outline.set(qn("w:val"), str(level - 1))
        ppr.append(outline)

    caption = document.styles["Caption"]
    caption.font.name = template.body_font_cn
    caption.font.size = Pt(template.caption_size_pt)
    caption.font.bold = False
    caption.font.italic = False
    caption.font.color.rgb = RGBColor(0, 0, 0)
    _set_rfonts(caption.element.get_or_add_rPr(), template.body_font_en, template.body_font_cn)
    cap_fmt = caption.paragraph_format
    cap_fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_fmt.first_line_indent = Pt(0)
    cap_fmt.space_before = Pt(3)
    cap_fmt.space_after = Pt(6)
    cap_fmt.line_spacing = 1.0


def _set_cell_text(cell, text: str, bold: bool, template: Template) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if bold else WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run(text)
    _run_fonts(run, template.body_font_en, template.body_font_cn, template.caption_size_pt, bold)


def _rule(element, edge: str, size_pt: float) -> None:
    border = OxmlElement(f"w:{edge}")
    border.set(qn("w:val"), "single")
    border.set(qn("w:sz"), str(int(round(size_pt * 8))))
    border.set(qn("w:space"), "0")
    border.set(qn("w:color"), "000000")
    element.append(border)


def _three_line_table(table, template: Template) -> None:
    """Strip the grid and draw only top, header, and bottom rules."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_pr = table._tbl.tblPr
    for old in tbl_pr.findall(qn("w:tblBorders")):
        tbl_pr.remove(old)
    borders = OxmlElement("w:tblBorders")
    _rule(borders, "top", template.table_rule_pt)
    for edge in ("left", "bottom", "right", "insideH", "insideV"):
        if edge == "bottom":
            _rule(borders, "bottom", template.table_rule_pt)
        else:
            empty = OxmlElement(f"w:{edge}")
            empty.set(qn("w:val"), "none")
            empty.set(qn("w:sz"), "0")
            empty.set(qn("w:space"), "0")
            borders.append(empty)
    tbl_pr.append(borders)

    header_row = table.rows[0]
    for cell in header_row.cells:
        tc_pr = cell._tc.get_or_add_tcPr()
        for old in tc_pr.findall(qn("w:tcBorders")):
            tc_pr.remove(old)
        cell_borders = OxmlElement("w:tcBorders")
        _rule(cell_borders, "bottom", template.table_header_rule_pt)
        tc_pr.append(cell_borders)


def _placeholder(document, text: str, template: Template) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(6)
    ppr = paragraph._p.get_or_add_pPr()
    p_borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        line = OxmlElement(f"w:{edge}")
        line.set(qn("w:val"), "dashed")
        line.set(qn("w:sz"), "6")
        line.set(qn("w:space"), "6")
        line.set(qn("w:color"), "808080")
        p_borders.append(line)
    ppr.append(p_borders)
    run = paragraph.add_run(text)
    _run_fonts(run, template.body_font_en, template.body_font_cn, template.caption_size_pt)


def _add_toc(document, template: Template) -> None:
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.first_line_indent = Pt(0)
    title.paragraph_format.space_after = Pt(12)
    run = title.add_run("目  录")
    _run_fonts(run, template.heading_font, template.heading_font, 16, bold=True)

    toc_paragraph = document.add_paragraph()
    toc_paragraph.paragraph_format.first_line_indent = Pt(0)
    _add_field(toc_paragraph, 'TOC \\o "1-3" \\h \\z \\u', "右键单击此处，选择“更新域”生成目录。")

    hint = document.add_paragraph()
    hint.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hint.paragraph_format.first_line_indent = Pt(0)
    hint.paragraph_format.space_before = Pt(12)
    hint_run = hint.add_run("（提交前请右键目录 → “更新域” → “更新整个目录”）")
    _run_fonts(hint_run, template.body_font_en, template.body_font_cn, 9)
    hint_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def _add_cover(document, front: FrontMatter, published: date_cls, template: Template) -> None:
    def centered(text: str, size: float, bold: bool = False, before: float = 0) -> None:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        paragraph.paragraph_format.space_before = Pt(before)
        run = paragraph.add_run(text)
        _run_fonts(run, template.body_font_en, template.heading_font, size, bold)

    centered(front.institution, 16, True, 24)
    centered(front.title, 26, True, 72)

    for value in (front.author, front.major and f"专业：{front.major}", front.advisor and f"指导教师：{front.advisor}"):
        if value:
            centered(value, 14, False, 18)
    centered(f"{published.year} 年 {published.month} 月", 14, False, 72)


def _add_header_footer(section, front: FrontMatter, template: Template) -> None:
    header = section.header
    header.is_linked_to_previous = False
    paragraph = header.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(front.header)
    _run_fonts(run, template.body_font_en, template.body_font_cn, template.header_text_size_pt)
    run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_field(paragraph, "PAGE", "1")
    for run in paragraph.runs:
        _run_fonts(
            run, template.body_font_en, template.body_font_cn, template.page_number_size_pt
        )


def _add_document_properties(document, front: FrontMatter, published: date_cls) -> None:
    core = document.core_properties
    core.title = front.title
    core.author = front.author
    core.last_modified_by = front.author
    core.subject = "Thesis built with thesis-forge"
    core.category = "Thesis"
    core.comments = "Generated from Markdown; verify against the official school template."
    stamp = datetime(published.year, published.month, published.day, 9, 0, 0)
    core.created = stamp
    core.modified = stamp
    core.revision = 1
    core.keywords = "thesis, thesis-forge, markdown"


class _Renderer:
    def __init__(self, document, front: FrontMatter, template: Template, base_dir: Path) -> None:
        self.document = document
        self.front = front
        self.template = template
        self.base_dir = base_dir
        self.figure_count = 0
        self.table_count = 0
        self.in_references = False
        self.warnings: list[str] = []
        self._bold = 0
        self._italic = 0

    # ---- inline ---------------------------------------------------------
    def inline(self, paragraph, token) -> None:
        for child in token.children or []:
            kind = child.type
            if kind == "text":
                self._run(paragraph, child.content)
            elif kind == "softbreak":
                paragraph.add_run().add_break()
            elif kind == "hardbreak":
                paragraph.add_run().add_break()
            elif kind == "code_inline":
                run = self._run(paragraph, child.content)
                run.font.name = "Consolas"
                _set_rfonts(run._r.get_or_add_rPr(), "Consolas", self.template.body_font_cn)
            elif kind == "strong_open":
                self._bold += 1
            elif kind == "strong_close":
                self._bold -= 1
            elif kind == "em_open":
                self._italic += 1
            elif kind == "em_close":
                self._italic -= 1
            elif kind == "link_open":
                continue
            elif kind == "link_close":
                continue
            elif kind == "image":
                self.figure(paragraph, child)

    def _run(self, paragraph, text: str):
        run = paragraph.add_run(text)
        _run_fonts(
            run,
            self.template.body_font_en,
            self.template.body_font_cn,
            self.template.body_size_pt,
            bold=self._bold > 0,
        )
        if self._italic > 0:
            run.font.italic = True
        return run

    def _caption(self, prefix: str, number: int, text: str, keep_next: bool) -> None:
        paragraph = self.document.add_paragraph(style="Caption")
        paragraph.paragraph_format.keep_with_next = keep_next
        label = f"{prefix} {number}"
        run = paragraph.add_run(label)
        _run_fonts(
            run,
            self.template.body_font_en,
            self.template.body_font_cn,
            self.template.caption_size_pt,
            bold=True,
        )
        if text:
            separator = paragraph.add_run("  ")
            _run_fonts(
                separator,
                self.template.body_font_en,
                self.template.body_font_cn,
                self.template.caption_size_pt,
            )
            body = paragraph.add_run(text)
            _run_fonts(
                body,
                self.template.body_font_en,
                self.template.body_font_cn,
                self.template.caption_size_pt,
            )

    # ---- blocks ---------------------------------------------------------
    def heading(self, level: int, token) -> None:
        level = min(level, 3)
        paragraph = self.document.add_paragraph(style=f"Heading {level}")
        text = token.content.strip()
        run = paragraph.add_run(text)
        size = {
            1: self.template.heading_size_h1_pt,
            2: self.template.heading_size_h2_pt,
            3: self.template.heading_size_h3_pt,
        }[level]
        _run_fonts(
            run, self.template.heading_font, self.template.heading_font, size, bold=True
        )
        self.in_references = text.strip().lower() in REFERENCE_HEADINGS

    def paragraph(self, token) -> None:
        stripped = token.content.strip()
        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            formula = self.document.add_paragraph()
            formula.alignment = WD_ALIGN_PARAGRAPH.CENTER
            formula.paragraph_format.first_line_indent = Pt(0)
            formula.paragraph_format.space_before = Pt(6)
            formula.paragraph_format.space_after = Pt(6)
            run = formula.add_run(stripped[2:-2].strip())
            _run_fonts(run, "Cambria Math", self.template.body_font_cn, self.template.body_size_pt)
            run.font.italic = True
            return
        paragraph = self.document.add_paragraph()
        if self.in_references:
            paragraph.paragraph_format.first_line_indent = Pt(-24)
            paragraph.paragraph_format.left_indent = Pt(24)
        else:
            paragraph.paragraph_format.keep_together = False
        self.inline(paragraph, token)

    def figure(self, paragraph, token) -> None:
        self.figure_count += 1
        number = self.figure_count
        alt = (token.content or "").strip()
        source = (token.attrGet("src") or "").strip()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        paragraph.paragraph_format.space_before = Pt(6)

        usable_cm = (
            self.template.page_width_cm
            - self.template.margin_left_cm
            - self.template.margin_right_cm
        )
        path = (self.base_dir / source).resolve()
        added = False
        if source and path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            try:
                paragraph.add_run().add_picture(str(path), width=Cm(usable_cm))
                added = True
            except (UnrecognizedImageError, OSError, ValueError) as exc:
                self.warnings.append(f"figure {number}: cannot embed {source}: {exc}")
        else:
            self.warnings.append(f"figure {number}: missing image {source or '(no src)'}")
        if not added:
            _placeholder(self.document, f"[缺图 / missing figure: {source}]", self.template)
        self._caption("图", number, alt, keep_next=False)

    def table(self, rows: list[list[str]], has_header: bool, caption: str) -> None:
        self.table_count += 1
        number = self.table_count
        if rows:
            columns = max(len(row) for row in rows)
        else:
            columns = 0
        self._caption("表", number, caption, keep_next=True)
        table = self.document.add_table(rows=len(rows), cols=max(columns, 1))
        for row_index, row in enumerate(rows):
            for column_index in range(columns):
                value = row[column_index] if column_index < len(row) else ""
                _set_cell_text(
                    table.cell(row_index, column_index),
                    value,
                    bold=has_header and row_index == 0,
                    template=self.template,
                )
        _three_line_table(table, self.template)
        spacer = self.document.add_paragraph()
        spacer.paragraph_format.first_line_indent = Pt(0)
        spacer.paragraph_format.space_after = Pt(0)


_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _split_table_row(line: str) -> list[str]:
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") else body
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def _normalize_tables(body: str) -> str:
    """Make every table row match the header's column count.

    markdown-it drops cells past the header width, which loses data without a
    word. Rows that are too long get their tail joined into the last cell;
    short rows are padded so cells stay under the right heading.
    """
    lines = body.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            index + 1 < len(lines)
            and "|" in line
            and _TABLE_SEP_RE.match(lines[index + 1])
        ):
            columns = len(_split_table_row(line))
            out.extend([line, lines[index + 1]])
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = _split_table_row(lines[index])
                if len(cells) > columns:
                    cells = cells[: columns - 1] + [" ".join(cells[columns - 1 :])]
                cells.extend([""] * (columns - len(cells)))
                out.append("| " + " | ".join(cells) + " |")
                index += 1
            continue
        out.append(line)
        index += 1
    return "\n".join(out)


def _collect_tables(tokens) -> list[dict]:
    """Group table tokens into ``{"caption": str, "rows": [[...]], "header": bool}``."""
    tables: list[dict] = []
    pending_caption = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "paragraph_open":
            inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
            following = tokens[index + 3] if index + 3 < len(tokens) else None
            if (
                inline_token is not None
                and inline_token.type == "inline"
                and following is not None
                and following.type == "table_open"
            ):
                match = CAPTION_PREFIX.match(inline_token.content.strip())
                if match:
                    pending_caption = match.group(1).strip()
                    index += 3
                    continue
        if token.type == "table_open":
            table: dict = {"caption": pending_caption, "rows": [], "header": False}
            pending_caption = ""
            rows = table["rows"]
            current_row: list[str] = []
            index += 1
            while index < len(tokens) and tokens[index].type != "table_close":
                kind = tokens[index].type
                if kind == "thead_open":
                    table["header"] = True
                elif kind in ("tr_open", "tr_close"):
                    if kind == "tr_close":
                        rows.append(current_row)
                        current_row = []
                elif kind in ("th_open", "td_open"):
                    inline_token = tokens[index + 1]
                    current_row.append(inline_token.content if inline_token.type == "inline" else "")
                index += 1
            tables.append(table)
        index += 1
    return tables


def build(
    source: Path,
    output: Path,
    template: Template | None = None,
    build_date: date_cls | None = None,
) -> BuildResult:
    """Build ``source`` into ``output``. Returns warnings instead of failing on them."""
    template = template or Template()
    text = source.read_text(encoding="utf-8")
    front, body = parse_front_matter(text)
    body = _normalize_tables(body)
    published = build_date or front.parsed_date
    if not front.date:
        front = replace(front, date=published.isoformat())

    document = Document()
    _set_page_geometry(document.sections[0], template)
    _patch_styles(document, template)
    _add_document_properties(document, front, published)
    _add_header_footer(document.sections[0], front, template)
    _add_cover(document, front, published, template)
    document.add_page_break()
    _add_toc(document, template)

    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = parser.parse(body)
    renderer = _Renderer(document, front, template, source.parent)
    tables = _collect_tables(tokens)
    table_index = 0

    index = 0
    while index < len(tokens):
        token = tokens[index]
        kind = token.type
        if kind == "heading_open":
            level = int(token.tag[1])
            renderer.heading(level, tokens[index + 1])
            index += 3
            continue
        if kind == "paragraph_open":
            inline_token = tokens[index + 1]
            following = tokens[index + 3] if index + 3 < len(tokens) else None
            if (
                following is not None
                and following.type == "table_open"
                and CAPTION_PREFIX.match(inline_token.content.strip())
            ):
                index += 3
                continue
            renderer.paragraph(inline_token)
            index += 3
            continue
        if kind == "table_open":
            table = tables[table_index] if table_index < len(tables) else {"caption": "", "rows": [], "header": False}
            table_index += 1
            renderer.table(table["rows"], table["header"], table["caption"])
            while index < len(tokens) and tokens[index].type != "table_close":
                index += 1
            index += 1
            continue
        if kind == "bullet_list_open" or kind == "ordered_list_open":
            ordered = kind == "ordered_list_open"
            index += 1
            counter = 0
            while index < len(tokens) and tokens[index].type not in (
                "bullet_list_close",
                "ordered_list_close",
            ):
                if tokens[index].type == "list_item_open":
                    counter += 1
                    inline_token = tokens[index + 2] if index + 2 < len(tokens) else None
                    if inline_token is not None and inline_token.type == "inline":
                        paragraph = document.add_paragraph()
                        marker = f"{counter}. " if ordered else "• "
                        run = paragraph.add_run(marker)
                        _run_fonts(
                            run,
                            template.body_font_en,
                            template.body_font_cn,
                            template.body_size_pt,
                        )
                        renderer.inline(paragraph, inline_token)
                index += 1
            index += 1
            continue
        if kind == "fence" or kind == "code_block":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.left_indent = Pt(24)
            paragraph.paragraph_format.line_spacing = 1.0
            run = paragraph.add_run(token.content.rstrip("\n"))
            _run_fonts(run, "Consolas", template.body_font_cn, 9)
            index += 1
            continue
        if kind == "blockquote_open":
            index += 1
            while index < len(tokens) and tokens[index].type != "blockquote_close":
                if tokens[index].type == "paragraph_open":
                    paragraph = document.add_paragraph()
                    paragraph.paragraph_format.left_indent = Pt(24)
                    renderer.inline(paragraph, tokens[index + 1])
                    for run in paragraph.runs:
                        run.font.italic = True
                index += 1
            index += 1
            continue
        if kind == "html_block":
            index += 1
            continue
        index += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return BuildResult(
        path=output,
        warnings=renderer.warnings,
        figure_count=renderer.figure_count,
        table_count=renderer.table_count,
    )


def build_metadata() -> dict[str, str]:
    return {"generator": f"thesis-forge {__version__}"}
