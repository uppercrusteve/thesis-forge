from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

BASE_MARKDOWN = """\
---
title: "测试论文"
author: "测试作者"
institution: "测试大学"
major: "测试专业"
advisor: "测试导师"
date: "2026-11-17"
header_text: "测试大学学位论文"
---

# 1 引言

这是第一段正文，包含中文标点。

![示例图题](figures/fig.png)

表: 示例表题

| 甲 | 乙 |
| --- | --- |
| 1 | 2 |

## 1.1 子节

子节正文，如图 1 所示。

# 参考文献

[1] 测试文献. 测试期刊, 2026.
"""

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "fig.png").write_bytes(TINY_PNG)
    path = tmp_path / "thesis.md"
    path.write_text(BASE_MARKDOWN, encoding="utf-8")
    return path


@pytest.fixture()
def built(source: Path, tmp_path: Path):
    from thesis_forge.render import build

    output = tmp_path / "out" / "thesis.docx"
    result = build(source, output)
    return result, output


def read_zip(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name)
