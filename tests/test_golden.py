"""End-to-end OCR regression checks against confirmed screenshots."""
import os
import re
import sys

import yaml
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import extract_quiz as q


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_confirmed_screenshot_extractions():
    with open(os.path.join(FIXTURE_DIR, "manifest.yaml"), encoding="utf-8") as f:
        fixtures = yaml.safe_load(f)["fixtures"]

    for fixture in fixtures:
        with Image.open(os.path.join(FIXTURE_DIR, fixture["image"])) as image:
            data = q.extract_quiz_data(image)

        assert data is not None, fixture["image"]
        assert data["category"] == fixture["category"]
        assert data["question"] == fixture["question"]
        normalize_answer = lambda value: re.sub(r"\s+", "", value).casefold()
        assert {
            number: normalize_answer(answer)
            for number, answer in data["answers"].items()
        } == {
            number: normalize_answer(answer)
            for number, answer in fixture["answers"].items()
        }
        assert data["correct"] == fixture["correct"]
        assert q.has_question_image(data["question_image"]) is fixture["image_present"]
        if fixture["image_present"]:
            assert data["question_image"].size == (488, 186)
