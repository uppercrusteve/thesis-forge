# 方法与假设

本文档记录 thesis-forge 采用的版式数值、OOXML 实现、检查规则与已知局限。所有数值是**通用基线**，不是对任何一所学校的承诺。

## 1. 依据

- GB/T 7713.1—2006《学位论文编写规则》：封面要素、章节编号、图表与参考文献的位置关系。
- GB/T 7714—2015《信息与文献 参考文献著录规则》：顺序编码制与方括号编号。
- ECMA-376 / ISO 29500 WordprocessingML：页面、样式、域、边框的实现方式。
- 常见高校研究生院模板的公共部分：A4、左侧装订边距、三线表、图题下/表题上、首行缩进 2 字符、1.5 倍行距。

与学校模板冲突时，以学校文件为准，并用 `--template` 覆盖。

## 2. 页面几何

| 项目 | 值 | OOXML |
| --- | --- | --- |
| 纸张 | A4，21 × 29.7 cm | `w:pgSz w:w="11906" w:h="16838"`（twip，四舍五入） |
| 上/下边距 | 2.54 cm | `w:pgMar w:top/bottom="1440"` |
| 左边距 | 3.0 cm | `w:left="1701"` |
| 右边距 | 2.5 cm | `w:right="1417"` |
| 可用宽度 | 15.5 cm | 由页宽减左右边距 |

单位换算：1 cm = 567 twip（1 twip = 1/1440 in），1 pt = 20 twip。代码用 `docx.shared.Cm/Pt` 转 EMU 后由 python-docx 写入 twip。

## 3. 字体与段落

- Normal：中文 `w:eastAsia="宋体"`，西文 `w:ascii="Times New Roman"`，12 pt（`w:sz="24"` 半磅）。
- 首行缩进：`firstLineChars="200"`（2 字符）与 `firstLine="480"` twip（2 × 12 pt × 20）。同时写两者，保证 Word 与只读字符数的解析器一致。
- 行距：1.5 倍，`w:spacing w:line="360" w:lineRule="auto"`（240 × 1.5）。
- 对齐：两端对齐（`w:jc="both"`）。
- Heading 1–3：黑体，18/15/13 pt（小二/小三/小三加粗视觉），段前 12 pt、段后 6 pt，`w:outlineLvl` 0/1/2；Heading 1 段前分页。
- 中文字体必须写 `w:eastAsia`，否则 Word 按主题字体回退，黑体/宋体设置会失效。

字号换算：`w:sz` 以半磅计，18 pt → 36，以此类推。

## 4. 页眉、页脚、目录

- 页眉：`header_text` 居中，9 pt；为空时回退到标题。
- 页脚：居中 PAGE 域（`begin` / `instrText " PAGE "` / `separate` / 结果 / `end`）。
- 目录：`TOC \o "1-3" \h \z \u` 复杂域，占位文字提示更新。开关含义：`\o "1-3"` 收集 1–3 级标题，`\h` 超链接，`\z` 隐藏页码，`\u` 使用大纲级别。
- 页码与目录条目由 Word 更新域生成；构建时**不伪造**页码，避免与最终排版不一致。

## 5. 表格

三线表通过 `w:tblBorders` 实现：

- 顶线、底线：1.5 pt（`w:sz="12"`，八分之一磅）。
- 表头下横线：0.75 pt（`w:sz="6"`），写在首行单元格的 `w:tcBorders`。
- 左、右、内竖线、内横线：`w:val="none"`。
- 表题在表格上方，`keep_with_next`；表体 10.5 pt，表头加粗居中。

## 6. 图表编号与缩放

- 图：`![图题](path)`，图题在图下；表：前一行 `表: 图题`，题注在表上。
- 计数器按文档顺序从 1 递增，输出“图 N”“表 N”。
- 图片按可用页宽 15.5 cm 等比缩放，只指定宽度，由 python-docx 保持纵横比。
- 缺图或格式无法识别时输出虚线占位框并写入警告；不中断构建。

## 7. 参考文献

`# 参考文献` 或 `References` 标题之后，段落设置左缩进 24 pt、悬挂 24 pt（`w:ind w:left="480" w:hanging="480"`），形成顺序编码制的悬挂排版。文献内容本身不自动格式化，作者对 GB/T 7714 的著录项负责。

## 8. 文档属性

`docProps/core.xml` 写入 title、author、lastModifiedBy、created、modified、revision=1。创建时间来自 front matter 的 `date` 或 `--date`，固定为当天 09:00，便于可复现比较。`generator` 标记为 thesis-forge。

## 9. 检查规则

| 代码 | 级别 | 判据 |
| --- | --- | --- |
| `h1-numbering` | error | 一级标题不以 `N ` 或 `N.N ` 开头（摘要、参考文献、致谢、附录除外） |
| `heading-jump` | error | 相邻标题层级一次上升超过 1 |
| `empty-heading` | error | 标题文本为空 |
| `caption-duplicate` | error | 显式题注“图 N/表 N”重复 |
| `caption-gap` | error | 显式题注跳号或首条不是 1 |
| `figure-ref-range` | error | 正文“图 N”超过图片总数 |
| `reference-duplicate` | error | 参考文献编号重复 |
| `citation-range` | error | 正文 `[n]` 超出文献条数 |
| `empty-table` | error | 表格无数据行或数据单元格全空 |
| `mixed-punctuation` | warning | 汉字后紧跟 `, ; : ! ?` |
| `long-paragraph` | warning | 单段超过 800 字 |
| `h2-before-h1` | warning | 二级标题先于任何一级标题 |
| `uncited-references` | warning | 有文献表但正文无 `[n]` |
| `missing-references` | warning | 有 `[n]` 但无文献表 |

Front matter 会被替换为等量空行，行号与源文件一致。规则只做结构判断，不理解语义。

## 10. 已知局限

1. 封面是单一通用版式，不含校徽、分类号、学号、密级等字段。
2. 公式仅按纯文本居中，不解析 LaTeX，`\frac` 等命令原样保留。
3. 目录、页码、交叉引用依赖 Word 更新域；LibreOffice 可能显示不同。
4. 不支持合并单元格、脚注、批注、多栏、横向页。表格行多出的单元格会并入该行最后一列，不会按语义拆分。
5. 页眉页码从封面开始；部分学校要求封面与目录不编码。
6. 标点规则对英文缩写、时间、代码可能误报。
7. 生成的 .docx 使用 python-docx 默认模板的样式 ID，若学校要求特定 styleId，需要后处理。
8. 字体是否可用取决于系统；缺字体时 Word 会回退，但样式名仍被写入。

## 11. 参考实现

- python-docx：OOXML 读写。
- markdown-it-py：CommonMark token 流（显式启用 table 规则）。
- PyYAML：front matter 与模板解析。
- 目录与页码字段写法参考 ECMA-376 的 complex field 结构。
