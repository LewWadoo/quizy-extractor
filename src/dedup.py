#!/usr/bin/env python3
"""Deduplicate questions in data/quizy.org.

Winner rule (owner-approved): manual > perfect > needs_agent_review
> needs_human_review;
ties keep the entry with a real image, then the longer/cleaner one.
Duplicates are compared on normalized question text (ё→е, case/punct
insensitive). Losers are printed (and optionally removed with --apply).

Usage: python3 src/dedup.py [--org data/quizy.org] [--apply]
"""
import os
import re
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_quiz import (  # noqa: E402
    DEFAULT_ORG_FILE, normalize_question, QUALITY_RANK,
)


def parse_org(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"(?m)^\*\* (.+)$", text)
    header = parts[0]
    entries = []
    for i in range(1, len(parts), 2):
        entries.append([parts[i].strip(), parts[i + 1] if i + 1 < len(parts) else ""])
    return header, entries


def entry_quality(body):
    m = re.search(r":EXTRACTION_QUALITY:\s*(\S+)", body)
    return m.group(1) if m else "needs_agent_review"


def has_real_image(body):
    m = re.search(r":IMAGE_LINK:\s*(\S+)", body)
    return bool(m and m.group(1) != "nil")


def score(body):
    q = entry_quality(body)
    return (
        QUALITY_RANK.get(q, 0),
        1 if has_real_image(body) else 0,
        len(body),
    )


def find_dup_groups(entries):
    groups = {}
    for idx, (title, _body) in enumerate(entries):
        groups.setdefault(normalize_question(title), []).append(idx)
    return {k: v for k, v in groups.items() if len(v) > 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default=DEFAULT_ORG_FILE)
    ap.add_argument("--apply", action="store_true",
                    help="Actually remove losers; default is report-only")
    args = ap.parse_args()
    header, entries = parse_org(args.org)
    groups = find_dup_groups(entries)
    print(f"entries: {len(entries)}, duplicate groups: {len(groups)}")
    losers = set()
    for norm, idxs in groups.items():
        ranked = sorted(idxs, key=lambda i: score(entries[i][1]), reverse=True)
        winner = ranked[0]
        print(f"\n### {entries[winner][0]!r} (keep idx {winner}, "
              f"quality={entry_quality(entries[winner][1])}, "
              f"image={has_real_image(entries[winner][1])})")
        for i in ranked[1:]:
            print(f"    drop idx {i} (quality={entry_quality(entries[i][1])}, "
                  f"image={has_real_image(entries[i][1])})")
            losers.add(i)
    if args.apply and losers:
        kept = [e for i, e in enumerate(entries) if i not in losers]
        out = header
        for title, body in kept:
            out += "** " + title + "\n" + body
            if not out.endswith("\n"):
                out += "\n"
        with open(args.org, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\nRemoved {len(losers)} duplicates; {len(kept)} entries remain.")
    elif losers:
        print(f"\n{len(losers)} duplicates would be removed (rerun with --apply).")
    else:
        print("No duplicates found.")


if __name__ == "__main__":
    main()
