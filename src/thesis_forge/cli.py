"""Command line interface for thesis-forge."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_cls
from pathlib import Path

from . import __version__
from .frontmatter import FrontMatterError
from .lint import lint, summarize
from .render import build
from .template import SAMPLE_TEMPLATE, Template, TemplateError, load

SKELETON = """\
---
title: "论文题目"
author: "作者姓名"
institution: "××大学"
major: "××专业"
advisor: "指导教师"
date: "{today}"
header_text: "××大学学位论文"
---

# 1 引言

在这里写研究背景与问题。正文使用中文全角标点，首行缩进由排版器统一处理。示例引用见文献[1]。

# 2 材料与方法

## 2.1 研究区

插入图片时，替代文本会自动成为图题：

![研究区位置图](figures/study-area.png)

引用图片写作“如图 1 所示”。表格题注写在表格上一行：

表: 样地基本信息

| 样地 | 海拔 / m | 品种 |
| --- | --- | --- |
| P1 | 1850 | 赤霞珠 |

# 3 结果

# 4 讨论

# 5 结论

# 参考文献

[1] 作者. 文献题名[J]. 期刊名, 2026, 1(1): 1-10.
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thesis-forge",
        description="把 Markdown 学位论文构建为通用中文高校格式的 .docx，并做格式体检。",
        epilog="格式为通用基线，提交前请对照本校模板。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    init = sub.add_parser("init", help="生成带 front matter 的论文骨架")
    init.add_argument("-o", "--output", default="thesis.md", help="输出 Markdown 路径")
    init.add_argument("--force", action="store_true", help="覆盖已存在的文件")

    build_cmd = sub.add_parser("build", help="构建 .docx")
    build_cmd.add_argument("input", type=Path, help="Markdown 源文件")
    build_cmd.add_argument("-o", "--output", required=True, type=Path, help="输出 .docx 路径")
    build_cmd.add_argument("--template", type=Path, help="YAML 格式模板")
    build_cmd.add_argument("--date", help="封面日期，ISO 8601（YYYY-MM-DD）")

    check = sub.add_parser("check", help="格式体检（有错误时退出码 1）")
    check.add_argument("input", type=Path, help="待检查的 Markdown 文件")
    check.add_argument("--json", action="store_true", help="输出 JSON")

    template = sub.add_parser("template", help="导出可编辑的格式模板")
    template.add_argument("-o", "--output", default="template.yaml", help="输出 YAML 路径")
    template.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    return parser


def _write_new(path: Path, content: str, force: bool) -> int:
    if path.exists() and not force:
        print(f"错误: {path} 已存在（使用 --force 覆盖）", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"已写入 {path}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 1
    template = Template()
    if args.template:
        template = load(args.template)
    build_date = None
    if args.date:
        try:
            build_date = date_cls.fromisoformat(args.date)
        except ValueError:
            print(f"错误: --date 需要 YYYY-MM-DD，收到 {args.date!r}", file=sys.stderr)
            return 1
    result = build(args.input, args.output, template=template, build_date=build_date)
    for warning in result.warnings:
        print(f"警告: {warning}", file=sys.stderr)
    print(
        f"已构建 {result.path}（图 {result.figure_count}，表 {result.table_count}，"
        f"警告 {len(result.warnings)}）"
    )
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 1
    issues = lint(args.input.read_text(encoding="utf-8"))
    errors, warnings = summarize(issues)
    if args.json:
        print(
            json.dumps(
                {
                    "file": str(args.input),
                    "errors": errors,
                    "warnings": warnings,
                    "issues": [issue.as_dict() for issue in issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if issues:
            print(f"{'LEVEL':<8} {'LINE':>5}  {'CODE':<20} MESSAGE")
            for issue in issues:
                line = "-" if not issue.line else str(issue.line)
                print(f"{issue.severity.upper():<8} {line:>5}  {issue.code:<20} {issue.message}")
            print()
        print(f"检查完成: {errors} 个错误, {warnings} 个警告")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        if args.command == "init":
            return _write_new(Path(args.output), SKELETON.format(today=date_cls.today()), args.force)
        if args.command == "template":
            return _write_new(Path(args.output), SAMPLE_TEMPLATE, args.force)
        if args.command == "build":
            return _cmd_build(args)
        if args.command == "check":
            return _cmd_check(args)
    except (FrontMatterError, TemplateError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print("错误: 输入文件不是 UTF-8 编码，请另存为 UTF-8 后重试", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
