from __future__ import annotations

from pathlib import Path

from thesis_forge.lint import lint, summarize

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

CLEAN = """\
---
title: T
author: A
institution: I
---

# 1 引言

正文如图 1 所示，并引用文献[1]。

![图题](a.png)

表: 表题

| 甲 | 乙 |
| --- | --- |
| 1 | 2 |

# 参考文献

[1] 文献. 期刊, 2026.
"""


def _codes(text: str) -> set[str]:
    return {issue.code for issue in lint(text)}


def test_clean_document_has_no_issues():
    assert lint(CLEAN) == []


def test_clean_document_summary():
    assert summarize(lint(CLEAN)) == (0, 0)


def test_seed_file_hits_every_error_rule():
    text = (EXAMPLES / "seed_errors.md").read_text(encoding="utf-8")
    codes = _codes(text)
    expected = {
        "h1-numbering",
        "heading-jump",
        "empty-heading",
        "figure-ref-range",
        "caption-duplicate",
        "caption-gap",
        "reference-duplicate",
        "citation-range",
        "mixed-punctuation",
        "long-paragraph",
        "empty-table",
    }
    assert expected <= codes


def test_seed_file_exit_severity():
    text = (EXAMPLES / "seed_errors.md").read_text(encoding="utf-8")
    errors, warnings = summarize(lint(text))
    assert errors >= 9
    assert warnings >= 1


def test_h1_numbering_reports_missing_number():
    issues = lint("# 引言\n\n正文。\n")
    assert [issue.code for issue in issues] == ["h1-numbering"]


def test_unnumbered_front_matter_heading_is_allowed():
    issues = lint("# 摘要\n\n正文。\n\n# 1 引言\n")
    assert "h1-numbering" not in {issue.code for issue in issues}


def test_heading_jump_is_an_error():
    issues = lint("# 1 引言\n\n### 1.1.1 过深\n")
    jump = [issue for issue in issues if issue.code == "heading-jump"]
    assert len(jump) == 1
    assert jump[0].severity == "error"


def test_empty_heading():
    assert "empty-heading" in _codes("# 1 引言\n\n##\n\n正文。\n")


def test_figure_reference_out_of_range():
    issues = lint("# 1 引言\n\n如图 3 所示。\n\n![图题](a.png)\n")
    assert any(issue.code == "figure-ref-range" for issue in issues)


def test_figure_reference_in_range_is_clean():
    issues = lint("# 1 引言\n\n如图 1 所示。\n\n![图题](a.png)\n")
    assert "figure-ref-range" not in {issue.code for issue in issues}


def test_duplicate_caption():
    text = "# 1 引言\n\n图 1 甲\n\n![x](a.png)\n\n图 1 乙\n"
    assert "caption-duplicate" in _codes(text)


def test_caption_gap():
    text = "# 1 引言\n\n图 2 甲\n\n![x](a.png)\n"
    assert "caption-gap" in _codes(text)


def test_reference_duplicate_and_citation_range():
    text = (
        "# 1 引言\n\n引用[9]。\n\n# 参考文献\n\n[1] 甲.\n\n[1] 乙.\n"
    )
    codes = _codes(text)
    assert "reference-duplicate" in codes
    assert "citation-range" in codes


def test_mixed_punctuation_is_only_a_warning():
    issues = [issue for issue in lint("中文,后面\n") if issue.code == "mixed-punctuation"]
    assert issues and issues[0].severity == "warning"


def test_full_width_punctuation_is_clean():
    assert "mixed-punctuation" not in _codes("中文，后面。\n")


def test_long_paragraph_warns():
    text = "字" * 801 + "\n"
    issues = [issue for issue in lint(text) if issue.code == "long-paragraph"]
    assert issues and issues[0].severity == "warning"


def test_short_paragraph_does_not_warn():
    assert "long-paragraph" not in _codes("字" * 800 + "\n")


def test_empty_table_with_blank_body():
    text = "# 1 引言\n\n| 甲 | 乙 |\n| --- | --- |\n|  |  |\n"
    assert "empty-table" in _codes(text)


def test_table_with_data_is_clean():
    text = "# 1 引言\n\n| 甲 | 乙 |\n| --- | --- |\n| 1 | 2 |\n"
    assert "empty-table" not in _codes(text)


def test_front_matter_lines_do_not_shift_line_numbers():
    text = "---\ntitle: T\nauthor: A\ninstitution: I\n---\n\n# 引言\n"
    issue = lint(text)[0]
    assert issue.code == "h1-numbering"
    assert issue.line == 7


def test_uncited_references_warn():
    text = "# 1 引言\n\n正文。\n\n# 参考文献\n\n[1] 甲.\n"
    assert "uncited-references" in _codes(text)
