# Quizy Extractor — screenshot → Org quiz questions

Extracts Квизи quiz questions from phone screenshots into
the shared Org database in the separate [`quizy` repository](https://github.com/LewWadoo/quizy)
(one `** ` entry per question with
`:CATEGORY:`, `:ANSWER1-4:`, `:CORRECT:`, `:IMAGE_LINK:`,
`:EXTRACTION_QUALITY:` — one of `manual`, `perfect`,
`needs_agent_review`, `needs_human_review`).

Clone both repositories side-by-side so the configured database and image
paths work:

```bash
git clone https://github.com/LewWadoo/quizy.git
git clone https://github.com/LewWadoo/quizy-extractor.git
```

If you keep them elsewhere, pass `--org` and `--img-dir` or edit
`config.yaml`.

## Setup

```bash
sudo apt install tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
pip install pillow pytesseract numpy pyyaml pytest
```

## Usage

```bash
# Extract yesterday's screenshots (default)
python3 src/extract_quiz.py
# Everything in the screenshot dir
python3 src/extract_quiz.py --all
# A specific date / custom paths
python3 src/extract_quiz.py --date 2026-09-05 --dir /path/to/shots \
    --org ../quizy/data/quizy.org --img-dir ../quizy/images/
```

All defaults come from `config.yaml` (screenshot dir, layout
coordinates, OCR params, categories). CLI flags override config.

## Checks

```bash
python3 -m pytest tests/ -q        # includes confirmed screenshot OCR goldens
python3 src/dedup.py               # report duplicates (add --apply to merge)
python3 src/review.py              # deterministic 0-100 quality summary
```

Every run records per-screenshot status in `data/extraction_status.yaml`
(`extracted | duplicate | skipped | failed`) so work is never repeated.
`--limit N` caps a run; `--reprocess` forces redo. Extracted screenshot
questions are grouped alphabetically under `* Добавленные вопросы`;
`:EXTRACTION_QUALITY:` distinguishes verified `manual` entries from those
still needing review. Move a source screenshot to `processed/` only after
verifying its question, answers, and correct choice; leave skipped and
unreviewed screenshots in the intake directory.

Agentic review: `.opencode/reviewer.md` (judge) and
`.opencode/product_manager.md` (arbiter, escalates to human when unsure).
Full extraction procedure: `SKILL.md`.

## Layout

- `config.yaml` — all paths, 576×1280 geometry, OCR/image gates, vocabularies
- `src/extract_quiz.py` — canonical extractor (config-driven)
- `src/dedup.py` — duplicate finder
  (`manual > perfect > needs_agent_review > needs_human_review`)
- `src/review.py` — deterministic 0–100 scorer (vision-owning reviewer
  agent in `.opencode/` judges picture coherence on top)
- `../quizy/data/quizy.org` — shared question DB (currently 941 entries)
- `../quizy/images/` — 18 clean, screenshot-verified crops linked from the DB
- `tests/` — regression tests + confirmed screenshot OCR fixtures/manifest
