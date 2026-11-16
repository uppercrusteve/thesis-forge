# Changelog

## 0.1.0 — 2026-11-17

Initial release.

- `build`: Markdown + YAML front matter → A4 .docx with header, PAGE field, TOC field, Heading 1–3 outline levels, Song/Heiti typography, 2-character first-line indent, 1.5 line spacing, three-line tables, automatic figure/table captions, figure placeholders, hanging reference indent, and document properties.
- `check`: heading numbering and level jumps, figure reference range, caption duplicates/gaps, reference duplicates and citation range, mixed punctuation, long paragraphs, empty headings and tables; table and `--json` output, exit code 1 on errors.
- `init` and `template` scaffolding commands.
- YAML template overrides for fonts, sizes, spacing, and margins.
- Test suite that inspects the zipped OOXML; CI workflow.
