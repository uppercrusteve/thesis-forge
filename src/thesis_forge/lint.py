"""Format checks for thesis Markdown.

The linter is intentionally conservative. ``error`` means the manuscript will
almost certainly violate a school template (or reads as broken); ``warning``
means a human should look at it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from markdown_it import MarkdownIt

H1_NUMBERED = re.compile(r"^\d+(?:\.\d+)*\s+\S")
FIGURE_REFERENCE = re.compile(r"(?:如|见|参见|详见)?\s*图\s*(\d+)")
CAPTION = re.compile(r"^\s*(图|表)\s*(\d+)(?=\s|$|[：:、.])")
TABLE_CAPTION_LINE = re.compile(r"^\s*表\s*[:：]")
CITATION = re.compile(r"\[(\d+(?:\s*[,，\-–]\s*\d+)*)\]")
REFERENCE_ENTRY = re.compile(r"^\s*\[(\d+)\]")
MIXED_PUNCTUATION = re.compile(r"[一-鿿][,;:!?]")
CHINESE = re.compile(r"[一-鿿]")

MAX_PARAGRAPH_CHARS = 800
REFERENCE_HEADINGS = {"参考文献", "references", "bibliography"}
UNNUMBERED_HEADINGS = REFERENCE_HEADINGS | {"摘要", "abstract", "致谢", "附录", "目录"}

SEVERITY_ORDER = {"error": 0, "warning": 1}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    line: int
    message: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _expand_citations(content: str) -> list[int]:
    numbers: list[int] = []
    for group in CITATION.findall(content):
        for part in re.split(r"[,，]", group):
            bounds = re.split(r"[\-–]", part)
            try:
                if len(bounds) == 2:
                    low, high = int(bounds[0]), int(bounds[1])
                    if low <= high and high - low <= 200:
                        numbers.extend(range(low, high + 1))
                else:
                    numbers.append(int(part))
            except ValueError:
                continue
    return numbers


def _blank_front_matter(text: str) -> str:
    """Blank out a leading front matter block while preserving line numbers."""
    lines = text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip() != "---":
        return text
    for end in range(start + 1, len(lines)):
        if lines[end].strip() == "---":
            for index in range(start, end + 1):
                lines[index] = ""
            break
    return "\n".join(lines)


def lint(text: str) -> list[Issue]:
    """Return all issues found in ``text``, ordered by severity and line."""
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = parser.parse(_blank_front_matter(text))
    issues: list[Issue] = []
    images_in_document = _count_images(tokens)

    def add(severity: str, code: str, line: int, message: str) -> None:
        issues.append(Issue(severity, code, line, message))

    h1_seen = False
    previous_level = 0
    references: list[int] = []
    figures_seen: list[int] = []
    tables_seen: list[int] = []
    in_references = False
    citation_numbers: list[int] = []
    citation_lines: list[int] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        line = (token.map[0] + 1) if token.map else 0
        kind = token.type

        if kind == "heading_open":
            level = int(token.tag[1])
            inline_token = tokens[index + 1]
            heading = inline_token.content.strip()
            if heading:
                if level == 1:
                    h1_seen = True
                    if not H1_NUMBERED.match(heading) and heading.lower() not in UNNUMBERED_HEADINGS:
                        add(
                            "error",
                            "h1-numbering",
                            line,
                            f"一级标题缺少“1 引言”式编号: {heading}",
                        )
                elif level == 2 and not h1_seen:
                    add("warning", "h2-before-h1", line, "二级标题出现在任何一级标题之前")
                if previous_level and level - previous_level > 1:
                    add(
                        "error",
                        "heading-jump",
                        line,
                        f"标题层级跳跃: H{previous_level} → H{level}",
                    )
                previous_level = level
                in_references = heading.lower() in REFERENCE_HEADINGS
            else:
                add("error", "empty-heading", line, "标题内容为空")
            index += 3
            continue

        if kind == "paragraph_open":
            inline_token = tokens[index + 1]
            content = inline_token.content
            stripped = content.strip()
            if in_references:
                match = REFERENCE_ENTRY.match(stripped)
                if match:
                    references.append(int(match.group(1)))
                index += 3
                continue

            caption = CAPTION.match(stripped)
            if caption:
                kind_name = caption.group(1)
                number = int(caption.group(2))
                target = figures_seen if kind_name == "图" else tables_seen
                label = "图" if kind_name == "图" else "表"
                if number in target:
                    add("error", "caption-duplicate", line, f"{label}题注编号重复: {label} {number}")
                elif target and number != target[-1] + 1:
                    add(
                        "error",
                        "caption-gap",
                        line,
                        f"{label}题注编号跳号: {label} {target[-1]} → {label} {number}",
                    )
                elif not target and number != 1:
                    add("error", "caption-gap", line, f"{label}题注从 {label} {number} 开始，应为 1")
                target.append(number)
                index += 3
                continue
            if TABLE_CAPTION_LINE.match(stripped):
                index += 3
                continue

            out_of_range: set[int] = set()
            for match in FIGURE_REFERENCE.finditer(stripped):
                referenced = int(match.group(1))
                if referenced > images_in_document and referenced not in out_of_range:
                    out_of_range.add(referenced)
                    add(
                        "error",
                        "figure-ref-range",
                        line,
                        f"正文引用图 {referenced}，但全文只有 {images_in_document} 张图",
                    )

            for number in _expand_citations(stripped):
                citation_numbers.append(number)
                citation_lines.append(line)

            for _ in MIXED_PUNCTUATION.finditer(stripped):
                add(
                    "warning",
                    "mixed-punctuation",
                    line,
                    "中文后使用英文标点（如“中文,”），建议改为全角",
                )
                break

            if len(stripped) > MAX_PARAGRAPH_CHARS:
                add(
                    "warning",
                    "long-paragraph",
                    line,
                    f"段落 {len(stripped)} 字，超过 {MAX_PARAGRAPH_CHARS} 字",
                )
            index += 3
            continue

        if kind == "table_open":
            rows: list[list[str]] = []
            current: list[str] = []
            has_head = False
            while index < len(tokens) and tokens[index].type != "table_close":
                if tokens[index].type == "thead_open":
                    has_head = True
                elif tokens[index].type == "tr_close":
                    rows.append(current)
                    current = []
                elif tokens[index].type in ("th_open", "td_open"):
                    content = tokens[index + 1].content if tokens[index + 1].type == "inline" else ""
                    current.append(content.strip())
                index += 1
            body_rows = rows[1:] if has_head else rows
            body_cells = [cell for row in body_rows for cell in row]
            if not rows or not body_cells or not any(body_cells):
                add("error", "empty-table", line, "表格没有数据行或数据单元格为空")
            index += 1
            continue

        index += 1

    for line, number in zip(citation_lines, citation_numbers):
        if number > len(references):
            add(
                "error",
                "citation-range",
                line,
                f"正文引用 [{number}] 超出参考文献表范围（共 {len(references)} 条）",
            )
    duplicates = sorted({number for number in references if references.count(number) > 1})
    for number in duplicates:
        add("error", "reference-duplicate", 0, f"参考文献编号重复: [{number}]")
    if references and not any(citation_numbers):
        add("warning", "uncited-references", 0, "存在参考文献表但正文没有任何 [n] 引用")
    if citation_numbers and not references:
        add("warning", "missing-references", 0, "正文有 [n] 引用，但没有参考文献表")

    issues.sort(key=lambda item: (SEVERITY_ORDER.get(item.severity, 9), item.line, item.code))
    return issues


def _count_images(tokens) -> int:
    count = 0
    for token in tokens:
        if token.type == "inline":
            count += sum(1 for child in token.children or [] if child.type == "image")
    return count


def summarize(issues: list[Issue]) -> tuple[int, int]:
    errors = sum(1 for issue in issues if issue.severity == "error")
    return errors, len(issues) - errors
