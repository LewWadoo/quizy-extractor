# Skill: extract Квизи questions from screenshots → Org entries

Automated extraction of quiz questions from 576×1280 screenshots
(`config.yaml: screenshot_dir`) into `data/quizy.org`, with images,
dedup, and review gates.

## 1. Screen format (576×1280 portrait)

```
y=0-70       : Category title (center top) + close button (top-right)
y=70-80      : Transition zone (separator)
y=80-240     : QUESTION IMAGE (photo) - MAIN AREA (40px side margins)
y=240-260    : Timeout progress bar (green line)
y=280-580    : Question text (multi-line)
y=580-930    : Answers in 2x2 grid:  TL(ans1) TR(ans2) / BL(ans3) BR(ans4)
y=1000+      : Stats ("@ верно", "Следующий вопрос" — never extract)
```

All coordinates live in `config.yaml` (`layout_576x1280`); never hardcode.
Non-576px screenshots (e.g. future native Cubot P60 shots) are skipped
with a "needs a new layout profile" message — add a second profile, do
not stretch the old one.

## 2. Answer grid mapping (critical)

| Position | Index | OCR quadrant | Green-detect quadrant |
|----------|-------|--------------|----------------------|
| Top-Left | 1 | 20,580, 278,730 | 0,580, 288,730 |
| Top-Right | 2 | 298,580, 556,730 | 288,580, 576,730 |
| Bottom-Left | 3 | 20,780, 278,930 | 0,780, 288,930 |
| Bottom-Right | 4 | 298,780, 556,930 | 288,780, 576,930 |

Reading order ≠ grid order. Always OCR per quadrant.

## 3. Pipeline (`src/extract_quiz.py`)

1. **Files**: `get_files_for_date()` / `get_all_files()` over
   `screenshot_dir` (`--dir`, `--date`, `--all`).
2. **Category**: full-image OCR, validate against `known_categories`.
   Unknown → skip entry (never invent).
3. **Question**: region y=280–580, PSM 6, join multi-line, stop before
   answers/footers (`продолжить`, `верно`, `следующий вопрос`, timestamps).
4. **Answers**: per-quadrant OCR; exactly 4 required.
5. **CORRECT**: green-highlight detection; MUST succeed — empty CORRECT
   is a hard error, entry is skipped, never written guessed.
6. **Image**: region y=80–240 with 40px margins; gates in `config.yaml`
   (`image_gates`: content pixels, color variance, size, brightness,
   saturation). Most screenshots have NO photo → `IMAGE_LINK: nil` is
   the correct output. Save as `./images/<slug-sha1>.jpg` + autocontrast.
7. **Write**: append entry with `:ID:` (slug+sha1), `:CATEGORY:`,
   `:ANSWER1-4:`, `:CORRECT:`, `:IMAGE_LINK:`, `:EXTRACTION_QUALITY:
   needs_agent_review`. New entries are never `perfect` on arrival:
   agents improve them until they score ≥ 90 or give up and escalate
   to `needs_human_review`.
8. **Ledger**: every screenshot is recorded in
   `data/extraction_status.yaml` (`extracted | duplicate | skipped |
   failed`, with question/id/reason). Recorded shots are not
   reprocessed (unless `--reprocess`); questions already in the DB are
   recorded as `duplicate` and never appended twice.

## 4. After extraction

1. `python3 src/dedup.py --org data/quizy.org` — duplicates resolved by
   `manual > perfect > needs_agent_review > needs_human_review`, ties
   keep the imaged entry.
2. Reviewer agent (`.opencode/reviewer.md`) looks at the actual picture,
   scores 0–100, and either proposes corrections or escalates. Up to 3
   improvement passes, then `needs_human_review`.
3. product_manager agent (`.opencode/product_manager.md`) accepts /
   queues / escalates. Unclear cases go to the human.
4. `python3 -m pytest tests/ -q` must stay green. The confirmed-data
   gate covers `perfect`/`manual` entries only; the
   `needs_agent_review` queue may grow freely.

## 5. Validation checklist per entry

- [ ] 4 answers present, TL/TR/BL/BR order
- [ ] CORRECT from green highlight, never empty
- [ ] CATEGORY from known list
- [ ] IMAGE_LINK: real photo file OR nil (no UI artifacts: close button,
      timeout bar, category text)
- [ ] Full multi-line question text
- [ ] :ID: and :EXTRACTION_QUALITY: set
