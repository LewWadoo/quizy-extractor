"""DB invariants — anti-degradation gate for the shared quizy database.

Every sample already confirmed as correct must keep passing. Any change
to the extractor, config or DB that lowers quality fails here.
"""
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from extract_quiz import (  # noqa: E402
    CONFIG, DEFAULT_IMG_DIR, DEFAULT_ORG_FILE, normalize_question,
    generate_id, QUALITY_RANK,
)
from review import score_entry  # noqa: E402

KNOWN = set(CONFIG.get("known_categories") or [])
THRESHOLD = int((CONFIG.get("review") or {}).get("accept_threshold", 90))
ORG = DEFAULT_ORG_FILE


def load_entries():
    with open(ORG, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"(?m)^\*\* (.+)$", text)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


ENTRIES = load_entries()


def test_db_not_shrinking():
    # 883 entries after the 2026-09-17 dedup; must never silently lose data.
    assert len(ENTRIES) >= 883, f"entry count dropped to {len(ENTRIES)}"


def test_no_duplicates():
    seen = {}
    dups = []
    for title, _ in ENTRIES:
        key = normalize_question(title)
        if key in seen:
            dups.append((seen[key], title))
        seen[key] = title
    assert not dups, f"duplicate questions found: {dups[:5]}"


def test_schema_complete():
    bad = []
    for title, body in ENTRIES:
        for prop in ("ID", "CATEGORY", "CORRECT", "IMAGE_LINK",
                     "EXTRACTION_QUALITY", "ANSWER1", "ANSWER2",
                     "ANSWER3", "ANSWER4"):
            if not re.search(rf"^:{prop}:\s*\S", body, re.M):
                bad.append((title[:50], prop))
    assert not bad, f"entries missing properties: {bad[:5]}"


def test_categories_known():
    bad = []
    for title, body in ENTRIES:
        m = re.search(r"^:CATEGORY:\s*(.*)$", body, re.M)
        if not m or m.group(1).strip() not in KNOWN:
            bad.append(title[:50])
    assert not bad, f"unknown categories: {bad[:5]}"


def test_correct_in_range():
    bad = [t[:50] for t, b in ENTRIES
           if not re.search(r"^:CORRECT:\s*[1-4]\s*$", b, re.M)]
    assert not bad, f"bad CORRECT values: {bad[:5]}"


def test_quality_vocabulary():
    ranks = set(QUALITY_RANK)
    bad = []
    for title, body in ENTRIES:
        m = re.search(r"^:EXTRACTION_QUALITY:\s*(\S+)", body, re.M)
        if not m or m.group(1) not in ranks:
            bad.append(title[:50])
    assert not bad


def test_placeholders_only_in_unreviewed():
    bad = []
    for title, body in ENTRIES:
        if "not found]" in body and not (
                "needs_agent_review" in body or "needs_human_review" in body):
            bad.append(title[:50])
    assert not bad, f"broken entries not flagged for review: {bad}"


def test_ids_unique_and_stable():
    ids = re.findall(r"^:ID:\s*(\S+)", "\n".join(b for _, b in ENTRIES), re.M)
    assert len(ids) == len(ENTRIES)
    assert len(set(ids)) == len(ids), "duplicate IDs"
    # ID scheme stability: slug + sha1 (spot check)
    assert generate_id("Какого цвета Пакман?") == \
        "какого-цвета-пакман-09c43fe9"


def test_dedup_winners_kept():
    by_title = {}
    for title, body in ENTRIES:
        by_title.setdefault(title, []).append(body)
    # Пакман: exactly one, CORRECT 4; its auto-extracted photo was judged
    # bad by the owner, so IMAGE_LINK must be nil now.
    pak = by_title.get("Какого цвета Пакман?")
    assert pak is not None and len(pak) == 1
    assert ":CORRECT:    4" in pak[0] or ":CORRECT: 4" in pak[0]
    assert re.search(r":IMAGE_LINK:\s*nil", pak[0])
    # 1984 / громоотвод: exactly one each, photos likewise removed.
    for q in ("Кто написал роман «1984»?", "Кто изобрёл громоотвод?"):
        assert len(by_title.get(q, [])) == 1, q
        assert re.search(r":IMAGE_LINK:\s*nil", by_title[q][0]), q
    # Киза: exactly one, complete answers
    kiz = by_title.get("Для кого цветы в романе Дэниела Киза?")
    assert len(kiz) == 1 and "not found]" not in kiz[0]


def test_only_owner_approved_images_linked():
    import os
    good = {"qimg_real_01.jpg", "qimg_real_04.jpg", "qimg_real_05.jpg",
            "qimg_real_06.jpg", "qimg_real_07.jpg",
            "qimg_real_какой-фильм-заканчивается-сценой-с-подоб-7799d404.jpg",
            "qimg_real_в-каком-фильме-подобное-увлечение-стало--7f59f3f9.jpg",
            "qimg_real_главный-герой-какого-фильма-считал-подоб-e05af782.jpg",
            "qimg_real_с-каким-камнем-это-кольцо-03db3b68.jpg",
            "qimg_real_песня-какой-группы-посвящена-этим-цветам-7faed3e2.jpg",
            "qimg_real_какое-число-традиционно-написано-на-подо-7ca85a3a.jpg",
            "qimg_real_режиссер-какого-фильма-высадил-подобное--fca54e33.jpg",
            "qimg_real_в-какой-серии-фильмов-эта-птица-была-сим-0a6c5933.jpg",
            "qimg_real_прозвище-лошади-из-какого-сериала-совпад-e4d26c09.jpg",
            "qimg_real_у-какого-исполнителя-есть-песня-посвящен-c6422607.jpg",
            "qimg_real_в-каком-виде-спорта-используются-такие-б-9b6d43e5.jpg",
            "qimg_real_у-какой-группы-есть-песня-посвященная-эт-cfc9f80f.jpg",
            "qimg_real_кто-посвятил-популярную-песню-этому-живо-176b635a.jpg"}
    links = re.findall(r":IMAGE_LINK:\s*\./images/(\S+)", "\n".join(b for _, b in ENTRIES))
    assert set(links) <= good, f"unapproved images linked: {set(links) - good}"
    assert set(links) == good, "an approved image lost its entry"
    disk = set(os.listdir(DEFAULT_IMG_DIR))
    assert disk == good, f"images/ dir mismatch: {disk ^ good}"


def test_new_photo_questions_are_grouped():
    with open(ORG, encoding="utf-8") as f:
        text = f.read()
    _, added = text.split("\n* Добавленные вопросы\n", 1)
    added_ids = set(re.findall(r"^:ID:\s*(\S+)", added, re.M))
    expected_ids = {
        "в-каком-виде-спорта-используются-такие-б-9b6d43e5",
        "в-какой-серии-фильмов-эта-птица-была-сим-0a6c5933",
        "какой-фильм-заканчивается-сценой-с-подоб-7799d404",
        "песня-какой-группы-посвящена-этим-цветам-7faed3e2",
        "с-каким-камнем-это-кольцо-03db3b68",
        "у-какого-исполнителя-есть-песня-посвящен-c6422607",
    }
    assert expected_ids <= added_ids


def test_confirmed_entries_score_perfect():
    # Anti-degradation gate: every human-confirmed entry (perfect/manual)
    # must keep scoring 100. The needs_agent/needs_human review queue is
    # explicitly excluded — unreviewed extractions may score anything.
    bad = []
    for title, body in ENTRIES:
        m = re.search(r"^:EXTRACTION_QUALITY:\s*(\S+)", body, re.M)
        quality = m.group(1) if m else "needs_agent_review"
        if quality in ("perfect", "manual"):
            s, _ = score_entry(title, body, DEFAULT_IMG_DIR)
            if s != 100:
                bad.append((title[:50], s))
    assert not bad, f"confirmed entries degraded: {bad[:5]}"


def test_review_queue_uses_split_vocabulary():
    quals = [re.search(r"^:EXTRACTION_QUALITY:\s*(\S+)", b, re.M).group(1)
             for _, b in ENTRIES]
    assert set(quals) <= {"manual", "perfect",
                          "needs_agent_review", "needs_human_review"}
    assert "needs_human_review" not in quals
