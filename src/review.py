#!/usr/bin/env python3
"""Deterministic extraction-quality scorer (0-100 + checklist).

Used by regression tests and as the factual input to the opencode
`reviewer` agent (.opencode/reviewer.md), which adds OCR re-checks and
judgement on top. The product_manager agent consumes this score plus
the reviewer verdict.

Scoring (25 pts each):
  - answers: 4 non-empty, no "[Answer N not found]" placeholders
  - correct: CORRECT in {1,2,3,4}
  - category: one of config.yaml known_categories
  - image_consistency: IMAGE_LINK is nil (text-only question) or a path
    whose file exists on disk (question that needs its photo)

Usage:
  python3 src/review.py --org data/quizy.org            # whole DB summary
  python3 src/review.py --question "Какого цвета Пакман?" # single entry
"""
import os
import re
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_quiz import (  # noqa: E402
    CONFIG, DEFAULT_IMG_DIR, DEFAULT_ORG_FILE,
)

KNOWN = set(CONFIG.get("known_categories") or [])


def score_entry(title, body, img_dir=None):
    checks = {}
    answers = re.findall(r":ANSWER([1-4]):\s*(.*)", body)
    ans_texts = [a[1].strip() for a in answers]
    checks["answers"] = (
        len(answers) == 4
        and all(t and "not found]" not in t for t in ans_texts)
    )
    m = re.search(r":CORRECT:\s*(\S+)", body)
    checks["correct"] = bool(m and m.group(1) in ("1", "2", "3", "4"))
    c = re.search(r":CATEGORY:\s*(.*)", body)
    checks["category"] = bool(c and c.group(1).strip() in KNOWN)
    im = re.search(r":IMAGE_LINK:\s*(\S+)", body)
    if not im or im.group(1) == "nil":
        checks["image_consistency"] = True  # text-only question, nothing to verify
    else:
        base = img_dir or DEFAULT_IMG_DIR
        rel = im.group(1).replace("./images/", "")
        checks["image_consistency"] = os.path.exists(os.path.join(base, rel))
    score = sum(25 for v in checks.values() if v)
    return score, checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default=DEFAULT_ORG_FILE)
    ap.add_argument("--question", default=None)
    ap.add_argument("--img-dir", default=None)
    args = ap.parse_args()
    with open(args.org, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"(?m)^\*\* (.+)$", text)
    entries = [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]
    if args.question:
        entries = [(t, b) for t, b in entries if args.question in t]
    scores = []
    for title, body in entries:
        s, checks = score_entry(title, body, args.img_dir)
        scores.append(s)
        if args.question or s < 100:
            print(f"{s:3d}  {title[:70]}  {checks}")
    if scores and not args.question:
        import statistics
        print(f"\nentries={len(scores)} mean={statistics.mean(scores):.1f} "
              f"min={min(scores)} perfect100={sum(1 for s in scores if s == 100)}")


if __name__ == "__main__":
    main()
