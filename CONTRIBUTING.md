# Contributing

Thanks for helping. This project is small on purpose: keep dependencies few and behaviour predictable.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Before a pull request

```bash
ruff check .
pytest -q
```

Both must pass. For rendering changes, build `examples/sample_thesis.md` and check the result in Word, not only in the tests:

```bash
thesis-forge build examples/sample_thesis.md -o examples/out/sample.docx
```

## What to test

- Rendering: unzip the produced .docx and assert on the OOXML. A test that only checks file existence is not enough.
- Lint rules: one positive case and one near-miss negative case.
- CLI: exit codes, stderr messages, and `--json` shape.

## Data conventions

- Example data must say **synthetic**, **public**, or **measured** in the caption and in `docs/methods.md`.
- Chinese units and punctuation follow the sample; do not quietly change `cm`, `pt`, or the typographic defaults without a note.
- New format rules need a standard or a common-template reference in the PR description.

## Bug reports

Include the Python version, Word version, a minimal Markdown input, and the unexpected OOXML or screenshot. Remove private manuscript text before uploading.

## Scope

This is a generic baseline. School-specific templates belong in `templates/` as YAML overrides; heavy layout engines (LaTeX, LibreOffice automation) are out of scope for the core.
