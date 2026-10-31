"""Regression tests for question/category parsing (no OCR needed).

Guards the two fixed bugs: category leaking back into the title via the
prepend step, and the old chop of len(category) chars off a clean
question when the category sat on the previous OCR line.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from extract_quiz import parse_quiz_from_text  # noqa: E402


def test_category_on_own_line_not_leaked_or_chopped():
    text = ("Технический прогресс\n"
            "Кто ввел термин лошадиная сила в широкое употребление?\n"
            "Джеймс Уатт\n"
            "Следующий вопрос")
    cat, q, _ = parse_quiz_from_text(text)
    assert cat == "Технический прогресс"
    assert q == "Кто ввел термин лошадиная сила в широкое употребление?"


def test_category_prefix_same_line_stripped():
    text = ("Технический прогресс Кто изобрел громоотвод?\n"
            "Михаил Ломоносов\n"
            "Следующий вопрос")
    cat, q, _ = parse_quiz_from_text(text)
    assert q == "Кто изобрел громоотвод?"


def test_clean_question_untouched():
    text = ("Спорт\n"
            "Что такое иппон в дзюдо?\n"
            "Удар\n"
            "Следующий вопрос")
    cat, q, _ = parse_quiz_from_text(text)
    assert (cat, q) == ("Спорт", "Что такое иппон в дзюдо?")


def test_countdown_artifacts_are_removed_from_question():
    text = ("Кинематограф\n"
            "оо Е» 00:16 Автомобиль какой марки угнали главные герои фильма «Бумер»?\n"
            "BMW\nToyota")
    cat, q, _ = parse_quiz_from_text(text)
    assert cat == "Кинематограф"
    assert q == "Автомобиль какой марки угнали главные герои фильма «Бумер»?"
