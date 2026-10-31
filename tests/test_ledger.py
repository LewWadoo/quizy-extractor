"""Status ledger + dup-check unit tests (no OCR needed)."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

import extract_quiz as q  # noqa: E402


def test_ledger_roundtrip(tmp_path):
    ledger = str(tmp_path / "status.yaml")
    shots = q.load_ledger(ledger)
    assert shots == {}
    data = {"question": "Какого цвета Пакман?", "correct": 4}
    q.ledger_record(shots, "shot.jpg", "extracted", data)
    q.save_ledger(ledger, shots)
    back = q.load_ledger(ledger)
    assert back["shot.jpg"]["status"] == "extracted"
    assert back["shot.jpg"]["question"] == "Какого цвета Пакман?"
    assert back["shot.jpg"]["quality"] == "needs_agent_review"
    assert "processed_at" in back["shot.jpg"]


def test_ledger_record_failure_reason(tmp_path):
    ledger = str(tmp_path / "status.yaml")
    shots = {}
    q.ledger_record(shots, "bad.jpg", "failed",
                    reason="No green highlight found")
    q.save_ledger(ledger, shots)
    back = q.load_ledger(ledger)
    assert back["bad.jpg"]["status"] == "failed"
    assert "green" in back["bad.jpg"]["reason"]


def test_load_known_titles():
    titles = q.load_known_titles(q.DEFAULT_ORG_FILE)
    assert len(titles) >= 883
    assert q.normalize_question("Какого цвета Пакман?") in titles


def test_default_quality_is_agent_review(tmp_path):
    org = str(tmp_path / "t.org")
    data = {"question": "Тестовый вопрос?",
            "category": "Спорт",
            "answers": {1: "а", 2: "б", 3: "в", 4: "г"},
            "correct": 1}
    q.append_to_org(data, None, org)
    text = open(org, encoding="utf-8").read()
    assert ":EXTRACTION_QUALITY: needs_agent_review" in text
    assert ":IMAGE_LINK: nil" in text
