"""Unit tests for dedup normalization and winner rule."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from extract_quiz import normalize_question, QUALITY_RANK  # noqa: E402
from dedup import find_dup_groups, score  # noqa: E402


def test_normalize_yo_e_case_punct():
    assert (normalize_question("Сколько пятен на теле новорождённых далматинов?")
            == normalize_question("Сколько пятен на теле новорожденных далматинов?"))
    assert normalize_question("Кто написал роман «1984»?") == "кто написал роман 1984"


def test_find_dup_groups():
    entries = [("Какого цвета Пакман?", "a"), ("Какого цвета Пакман?", "b"),
               ("Другой вопрос?", "c")]
    groups = find_dup_groups(entries)
    assert len(groups) == 1
    assert groups[normalize_question("Какого цвета Пакман?")] == [0, 1]


def test_winner_rule_quality_first():
    manual = ":EXTRACTION_QUALITY: manual\n:IMAGE_LINK: nil\n"
    perfect_img = ":EXTRACTION_QUALITY: perfect\n:IMAGE_LINK: ./images/x.jpg\n"
    agent = ":EXTRACTION_QUALITY: needs_agent_review\n:IMAGE_LINK: ./images/x.jpg\n"
    human = ":EXTRACTION_QUALITY: needs_human_review\n:IMAGE_LINK: ./images/y.jpg\n"
    assert score(manual) > score(perfect_img) > score(agent) > score(human)


def test_winner_rule_image_breaks_ties():
    with_img = ":EXTRACTION_QUALITY: perfect\n:IMAGE_LINK: ./images/x.jpg\nxx"
    without = ":EXTRACTION_QUALITY: perfect\n:IMAGE_LINK: nil\n" + "x" * 200
    # image beats raw length
    assert score(with_img) > score(without)


def test_quality_rank_config():
    assert (QUALITY_RANK["manual"] > QUALITY_RANK["perfect"]
            > QUALITY_RANK["needs_agent_review"] > QUALITY_RANK["needs_human_review"])
