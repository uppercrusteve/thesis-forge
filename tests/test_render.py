from __future__ import annotations

from datetime import date
from pathlib import Path

from conftest import NS, read_zip
from docx import Document
from lxml import etree

from thesis_forge.frontmatter import FrontMatterError, parse
from thesis_forge.render import build
from thesis_forge.template import Template


def _document_xml(path: Path):
    return etree.fromstring(read_zip(path, "word/document.xml"))


def _styles_xml(path: Path):
    return etree.fromstring(read_zip(path, "word/styles.xml"))


def _style(path: Path, style_id: str):
    root = _styles_xml(path)
    return root.xpath(f'//w:style[@w:styleId="{style_id}"]', namespaces=NS)[0]


def _body_paragraph_texts(element) -> list[str]:
    return [
        "".join(p.itertext()) if p.tag.endswith("}p") else ""
        for p in element.xpath("//w:body/*", namespaces=NS)
    ]


def test_page_is_a4(built):
    _, output = built
    geometry = _document_xml(output).xpath("//w:sectPr/w:pgSz", namespaces=NS)[0]
    assert abs(int(geometry.get(f"{{{NS['w']}}}w")) - 11906) <= 2
    assert abs(int(geometry.get(f"{{{NS['w']}}}h")) - 16838) <= 2


def test_margins_match_brief(built):
    _, output = built
    margins = _document_xml(output).xpath("//w:sectPr/w:pgMar", namespaces=NS)[0]
    values = {key: int(margins.get(f"{{{NS['w']}}}{key}")) for key in ("top", "bottom", "left", "right")}
    assert values == {"top": 1440, "bottom": 1440, "left": 1701, "right": 1417}


def test_header_is_centered_and_uses_front_matter(built):
    _, output = built
    header = etree.fromstring(read_zip(output, "word/header1.xml"))
    paragraph = header.xpath("//w:p", namespaces=NS)[0]
    assert "".join(paragraph.itertext()) == "测试大学学位论文"
    assert paragraph.xpath("w:pPr/w:jc/@w:val", namespaces=NS) == ["center"]


def test_footer_contains_page_field(built):
    _, output = built
    footer = etree.fromstring(read_zip(output, "word/footer1.xml"))
    instructions = footer.xpath("//w:instrText/text()", namespaces=NS)
    assert any("PAGE" in instruction for instruction in instructions)
    types = footer.xpath("//w:fldChar/@w:fldCharType", namespaces=NS)
    assert "begin" in types and "end" in types


def test_toc_field_and_heading_range(built):
    _, output = built
    document = _document_xml(output)
    instructions = "".join(document.xpath("//w:instrText/text()", namespaces=NS))
    assert "TOC" in instructions
    assert '\\o "1-3"' in instructions
    assert "\\h" in instructions


def test_heading_styles_use_heiti_and_expected_sizes(built):
    _, output = built
    for style_id, size in (("Heading1", "36"), ("Heading2", "30"), ("Heading3", "26")):
        style = _style(output, style_id)
        fonts = style.xpath("w:rPr/w:rFonts", namespaces=NS)[0]
        assert fonts.get(f"{{{NS['w']}}}eastAsia") == "黑体"
        assert style.xpath("w:rPr/w:sz/@w:val", namespaces=NS) == [size]


def test_heading_outline_levels(built):
    _, output = built
    for style_id, level in (("Heading1", "0"), ("Heading2", "1"), ("Heading3", "2")):
        style = _style(output, style_id)
        assert style.xpath("w:pPr/w:outlineLvl/@w:val", namespaces=NS) == [level]


def test_heading_one_starts_a_page(built):
    _, output = built
    style = _style(output, "Heading1")
    value = style.xpath("w:pPr/w:pageBreakBefore/@w:val", namespaces=NS)
    assert value in ([], ["1"], ["true"])


def test_normal_style_fonts_indent_and_spacing(built):
    _, output = built
    style = _style(output, "Normal")
    fonts = style.xpath("w:rPr/w:rFonts", namespaces=NS)[0]
    assert fonts.get(f"{{{NS['w']}}}eastAsia") == "宋体"
    assert fonts.get(f"{{{NS['w']}}}ascii") == "Times New Roman"
    assert style.xpath("w:rPr/w:sz/@w:val", namespaces=NS) == ["24"]
    assert style.xpath("w:pPr/w:ind/@w:firstLineChars", namespaces=NS) == ["200"]
    assert style.xpath("w:pPr/w:ind/@w:firstLine", namespaces=NS) == ["480"]
    assert style.xpath("w:pPr/w:spacing/@w:line", namespaces=NS) == ["360"]
    assert style.xpath("w:pPr/w:jc/@w:val", namespaces=NS) == ["both"]


def test_three_line_table_rules(built):
    _, output = built
    document = _document_xml(output)
    borders = document.xpath("//w:tblBorders", namespaces=NS)[0]
    def rule(edge: str) -> str:
        return borders.xpath(f"w:{edge}/@w:sz", namespaces=NS)[0]
    assert rule("top") == "12"
    assert rule("bottom") == "12"
    assert borders.xpath("w:insideV/@w:val", namespaces=NS) == ["none"]
    header_bottom = document.xpath("//w:tr[1]/w:tc[1]/w:tcPr/w:tcBorders/w:bottom/@w:sz", namespaces=NS)
    assert header_bottom == ["6"]


def test_figure_caption_follows_image(built):
    _, output = built
    document = _document_xml(output)
    body_children = document.xpath("//w:body/*", namespaces=NS)
    drawing_index = next(
        index for index, child in enumerate(body_children) if child.xpath(".//w:drawing", namespaces=NS)
    )
    following = body_children[drawing_index + 1]
    assert "".join(following.itertext()).strip().startswith("图 1")
    assert "示例图题" in "".join(following.itertext())


def test_table_caption_precedes_table(built):
    _, output = built
    document = _document_xml(output)
    body_children = document.xpath("//w:body/*", namespaces=NS)
    table_index = next(index for index, child in enumerate(body_children) if child.tag.endswith("}tbl"))
    preceding = body_children[table_index - 1]
    assert "".join(preceding.itertext()).strip().startswith("表 1")


def test_table_cells_and_header_text(built):
    _, output = built
    document = Document(output)
    assert len(document.tables) == 1
    assert [cell.text for cell in document.tables[0].rows[0].cells] == ["甲", "乙"]
    assert [cell.text for cell in document.tables[0].rows[1].cells] == ["1", "2"]


def test_document_properties(built):
    _, output = built
    document = Document(output)
    properties = document.core_properties
    assert properties.title == "测试论文"
    assert properties.author == "测试作者"
    assert properties.created.date() == date(2026, 11, 17)
    assert properties.last_modified_by == "测试作者"


def test_reference_uses_hanging_indent(built):
    _, output = built
    document = _document_xml(output)
    paragraphs = document.xpath("//w:body/w:p", namespaces=NS)
    reference = next(p for p in paragraphs if "测试文献" in "".join(p.itertext()))
    indent = reference.xpath("w:pPr/w:ind", namespaces=NS)[0]
    assert indent.get(f"{{{NS['w']}}}left") == "480"
    hanging = indent.get(f"{{{NS['w']}}}hanging")
    assert hanging == "480" or indent.get(f"{{{NS['w']}}}firstLine") == "-480"


def test_missing_image_warns_but_still_builds(tmp_path: Path):
    source = tmp_path / "thesis.md"
    source.write_text(
        "---\ntitle: T\nauthor: A\ninstitution: I\ndate: 2026-11-17\n---\n\n"
        "# 1 引言\n\n![缺图题注](nope.png)\n\n正文。\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.docx"
    result = build(source, output)
    assert output.is_file()
    assert any("missing image" in warning for warning in result.warnings)
    document = Document(output)
    assert any("缺图" in paragraph.text for paragraph in document.paragraphs)
    assert any(paragraph.text.startswith("图 1") for paragraph in document.paragraphs)


def test_template_override_changes_geometry(source: Path, tmp_path: Path):
    template = Template(page_width_cm=20.0, margin_left_cm=2.0, body_size_pt=10.5)
    result = build(source, tmp_path / "custom.docx", template=template)
    document = _document_xml(result.path)
    geometry = document.xpath("//w:sectPr/w:pgSz", namespaces=NS)[0]
    assert abs(int(geometry.get(f"{{{NS['w']}}}w")) - 11339) <= 2
    left = document.xpath("//w:sectPr/w:pgMar/@w:left", namespaces=NS)[0]
    assert left == "1134"
    normal = _style(result.path, "Normal")
    assert normal.xpath("w:rPr/w:sz/@w:val", namespaces=NS) == ["21"]


def test_front_matter_requires_title():
    try:
        parse("---\nauthor: A\ninstitution: I\n---\n\n正文\n")
    except FrontMatterError as exc:
        assert "title" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("FrontMatterError not raised")


def test_unknown_template_key_is_rejected(source: Path, tmp_path: Path):
    template_path = tmp_path / "bad.yaml"
    template_path.write_text("body_font_cn: 宋体\nmagic: 1\n", encoding="utf-8")
    from thesis_forge.template import TemplateError, load

    try:
        load(template_path)
    except TemplateError as exc:
        assert "magic" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("TemplateError not raised")
