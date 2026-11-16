from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from thesis_forge.cli import main


def test_help_exits_zero_and_lists_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    for command in ("build", "check", "init", "template"):
        assert command in output


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_init_writes_front_matter(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "-o", "thesis.md"]) == 0
    text = (tmp_path / "thesis.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "title:" in text
    assert "# 1 引言" in text


def test_init_refuses_overwrite_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "thesis.md").write_text("old", encoding="utf-8")
    assert main(["init", "-o", "thesis.md"]) == 1
    assert "已存在" in capsys.readouterr().err
    assert main(["init", "-o", "thesis.md", "--force"]) == 0
    assert (tmp_path / "thesis.md").read_text(encoding="utf-8").startswith("---")


def test_build_missing_input(tmp_path, capsys):
    assert main(["build", str(tmp_path / "nope.md"), "-o", str(tmp_path / "out.docx")]) == 1
    assert "找不到输入文件" in capsys.readouterr().err


def test_build_invalid_front_matter(tmp_path, capsys):
    source = tmp_path / "bad.md"
    source.write_text("no front matter\n", encoding="utf-8")
    assert main(["build", str(source), "-o", str(tmp_path / "out.docx")]) == 1
    assert "front matter" in capsys.readouterr().err


def test_build_invalid_date(tmp_path, capsys):
    source = tmp_path / "ok.md"
    source.write_text(
        "---\ntitle: T\nauthor: A\ninstitution: I\n---\n\n# 1 引言\n", encoding="utf-8"
    )
    assert main(["build", str(source), "-o", str(tmp_path / "out.docx"), "--date", "17-11-2026"]) == 1
    assert "--date" in capsys.readouterr().err


def test_build_warns_on_missing_image_but_succeeds(tmp_path, capsys):
    source = tmp_path / "ok.md"
    source.write_text(
        "---\ntitle: T\nauthor: A\ninstitution: I\ndate: 2026-11-17\n---\n\n"
        "# 1 引言\n\n![缺](nope.png)\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.docx"
    assert main(["build", str(source), "-o", str(output)]) == 0
    assert output.is_file()
    assert "警告" in capsys.readouterr().err


def test_check_clean_file_exits_zero(tmp_path, capsys):
    source = tmp_path / "ok.md"
    source.write_text("# 1 引言\n\n正文。\n", encoding="utf-8")
    assert main(["check", str(source)]) == 0
    assert "0 个错误" in capsys.readouterr().out


def test_check_seed_exits_one_and_json(tmp_path, capsys):
    source = Path(__file__).resolve().parents[1] / "examples" / "seed_errors.md"
    assert main(["check", str(source), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"] >= 9
    assert any(issue["code"] == "caption-duplicate" for issue in payload["issues"])


def test_check_missing_file(tmp_path, capsys):
    assert main(["check", str(tmp_path / "nope.md")]) == 1
    assert "找不到输入文件" in capsys.readouterr().err


def test_template_command_writes_loadable_yaml(tmp_path, capsys):
    output = tmp_path / "template.yaml"
    assert main(["template", "-o", str(output)]) == 0
    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["page_width_cm"] == 21.0
    assert data["body_font_cn"] == "宋体"
    assert data["line_spacing"] == 1.5


def test_template_command_refuses_overwrite(tmp_path, capsys):
    output = tmp_path / "template.yaml"
    output.write_text("x: 1\n", encoding="utf-8")
    assert main(["template", "-o", str(output)]) == 1
    assert main(["template", "-o", str(output), "--force"]) == 0


def test_build_with_template(tmp_path):
    source = tmp_path / "ok.md"
    source.write_text(
        "---\ntitle: T\nauthor: A\ninstitution: I\ndate: 2026-11-17\n---\n\n# 1 引言\n\n正文。\n",
        encoding="utf-8",
    )
    template = tmp_path / "t.yaml"
    template.write_text("margin_left_cm: 2.0\n", encoding="utf-8")
    output = tmp_path / "out.docx"
    assert main(["build", str(source), "-o", str(output), "--template", str(template)]) == 0
    assert output.is_file()


def test_build_bad_template_reports_error(tmp_path, capsys):
    source = tmp_path / "ok.md"
    source.write_text(
        "---\ntitle: T\nauthor: A\ninstitution: I\n---\n\n# 1 引言\n", encoding="utf-8"
    )
    template = tmp_path / "t.yaml"
    template.write_text("unknown_key: 1\n", encoding="utf-8")
    assert main(["build", str(source), "-o", str(tmp_path / "o.docx"), "--template", str(template)]) == 1
    assert "unknown" in capsys.readouterr().err
