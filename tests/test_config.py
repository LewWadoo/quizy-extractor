"""Config + layout sanity: extractor must match config.yaml."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

import extract_quiz as q  # noqa: E402


def test_config_matches_extractor():
    assert q.LAYOUT["width"] == 576
    assert q.LAYOUT["height"] == 1280
    assert tuple(q.QUESTION_IMAGE_REGION) == (44, 252, 532, 438)
    assert q.DEFAULT_CACHE_DIR == os.path.expanduser(
        "~/Pictures/Screenshots/Квизи")
    assert q.DEFAULT_ORG_FILE.endswith(
        os.path.join("quizy", "data", "quizy.org"))
    assert os.path.normpath(q.DEFAULT_IMG_DIR).endswith(
        os.path.join("quizy", "images"))
    assert len(q.KNOWN_CATEGORIES) == 8


def test_regions_inside_image():
    w, h = q.LAYOUT["width"], q.LAYOUT["height"]
    for name in ("category_region", "question_text_region"):
        x1, y1, x2, y2 = q.LAYOUT[name]
        assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h, name
    seen = set()
    for num, box in q.LAYOUT["answer_quadrants"].items():
        x1, y1, x2, y2 = box
        assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h
        key = (x1, y1, x2, y2)
        assert key not in seen, f"quadrant {num} overlaps another"
        seen.add(key)
    x1, y1, x2, y2 = q.QUESTION_IMAGE_REGION
    assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h


def test_screenshot_dir_exists():
    assert os.path.isdir(q.DEFAULT_CACHE_DIR)


def test_green_detection_on_synthetic():
    from PIL import Image
    w, h = q.LAYOUT["width"], q.LAYOUT["height"]
    img = Image.new("RGB", (w, h), (20, 20, 25))
    # Paint quadrant 3 green (correct answer = 3)
    x1, y1, x2, y2 = q.LAYOUT["green_quadrants"][3]
    for y in range(y1, y2, 2):
        for x in range(x1, x2, 2):
            img.putpixel((x, y), (40, 200, 60))
    assert q.detect_green_answer(img) == 3


def test_green_detection_absent_raises():
    from PIL import Image
    img = Image.new("RGB", (576, 1280), (20, 20, 25))
    try:
        q.detect_green_answer(img)
    except ValueError as e:
        assert "CORRECT cannot be empty" in str(e)
    else:
        raise AssertionError("expected ValueError for imageless screen")


def test_extractor_rejects_wrong_layout_height():
    from PIL import Image
    img = Image.new("RGB", (576, 1279), (20, 20, 25))
    assert q.extract_quiz_data(img) is None


def test_image_gates_reject_text_only_cards():
    from PIL import Image
    card = Image.new("RGB", (488, 186), (18, 18, 20))
    assert q.extract_question_image(Image.new("RGB", (576, 1280), (18, 18, 20))) is None
    assert not q.has_question_image(card)


def test_image_gates_accept_low_saturation_photo():
    from PIL import Image
    fixture = os.path.join(REPO, "tests", "fixtures", "quiz-plant-image.jpg")
    with Image.open(fixture) as screenshot:
        image = q.extract_question_image(screenshot)
    assert image is not None
    assert image.size == (488, 186)
