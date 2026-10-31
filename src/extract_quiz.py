#!/usr/bin/env python3
"""
Extract quiz questions from screenshots (576x1280 quiz format).
Config-driven: see config.yaml for screenshot dir, org file, layout,
OCR params, known categories/patterns.
Usage: python3 src/extract_quiz.py [--config config.yaml] [--date YYYY-MM-DD]
       [--dir DIR] [--org ORG] [--img-dir IMGDIR] [--all]
"""

import os
import sys
import re
import argparse
from datetime import datetime, timedelta
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import hashlib
import numpy as np

try:
    import yaml
except ImportError:
    yaml = None


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path=None):
    """Load config.yaml; fall back to built-in defaults if pyyaml missing."""
    defaults = {
        "screenshot_dir": "~/Pictures/Screenshots/Квизи",
        "org_file": "../quizy/data/quizy.org",
        "img_dir": "../quizy/images/",
    }
    cfg_path = path or os.path.join(repo_root(), "config.yaml")
    if yaml is not None and os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        merged = dict(defaults)
        merged.update(cfg)
        return merged
    return defaults


CONFIG = load_config(os.environ.get("QUIZY_CONFIG"))
_cfg_ocr = CONFIG.get("ocr") or {}

# Configuration (overridable via config.yaml / CLI)
DEFAULT_CACHE_DIR = os.path.expanduser(
    CONFIG.get("screenshot_dir", "~/Pictures/Screenshots/Квизи"))
_org = CONFIG.get("org_file", "data/quizy.org")
DEFAULT_ORG_FILE = _org if os.path.isabs(_org) else os.path.join(repo_root(), _org)
_img = CONFIG.get("img_dir", "images/")
DEFAULT_IMG_DIR = _img if os.path.isabs(_img) else os.path.join(repo_root(), _img)

_cfg_layout = (CONFIG.get("layout_576x1280") or {})
_cfg_gates = (CONFIG.get("image_gates") or {})
_cfg_green = (_cfg_layout.get("green_threshold") or {})

# Known categories for validation
KNOWN_CATEGORIES = set(CONFIG.get("known_categories") or {
    "Вокруг света", "Гик-культура", "Искусство", "Кинематограф",
    "Поп-культура", "Природа", "Спорт", "Технический прогресс"
})

# Known answer patterns for splitting concatenated answers (from config.yaml;
# kept for compatibility — the reviewer agent decides whether still needed).
KNOWN_PATTERNS = list(CONFIG.get("known_patterns") or [
    'Бентли', 'Астон Мартин', 'Джагуар', 'Роллс-ройс',
])

# Layout for the 576x1280 quiz format. Values come from config.yaml
# (layout_576x1280); literals below are fallbacks for running without config.
def _quads(raw, fallback):
    try:
        return {int(k): tuple(v) for k, v in (raw or {}).items()}
    except Exception:
        return fallback

LAYOUT = {
    'width': _cfg_layout.get('width', 576),
    'height': _cfg_layout.get('height', 1280),
    # Full top bar for category detection (we'll search within this)
    'category_region': tuple(_cfg_layout.get('category_region', (0, 0, 576, 70))),
    # Question text: y=280-580
    'question_text_region': tuple(_cfg_layout.get('question_text_region', (20, 280, 556, 580))),
    # Answer quadrants: 2x2 grid at y=580-930
    'answer_quadrants': _quads(_cfg_layout.get('answer_quadrants'), {
        1: (20, 580, 278, 730),   # Top-Left
        2: (298, 580, 556, 730),  # Top-Right
        3: (20, 780, 278, 930),   # Bottom-Left
        4: (298, 780, 556, 930),  # Bottom-Right
    }),
    'answer_quadrants_with_image': _quads(
        _cfg_layout.get('answer_quadrants_with_image'), {
            1: (20, 550, 278, 700),
            2: (298, 550, 556, 700),
            3: (20, 710, 278, 860),
            4: (298, 710, 556, 860),
        }),
    # Green detection regions (slightly larger for better detection)
    'green_quadrants': _quads(_cfg_layout.get('green_quadrants'), {
        1: (0, 580, 288, 730),
        2: (288, 580, 576, 730),
        3: (0, 780, 288, 930),
        4: (288, 780, 576, 930),
    }),
}

# Question image region: y=80-240 with 40px margins (excludes close button)
QUESTION_IMAGE_REGION = tuple(_cfg_layout.get('question_image_region', (40, 80, 536, 240)))

# Green detection + photo gates from config
GREEN_DELTA = int(_cfg_green.get('delta', 20))
GREEN_MIN_G = int(_cfg_green.get('min_g', 60))
GREEN_MIN_PIXELS = int(_cfg_green.get('min_pixels', 30))
GATE_MIN_W = int(_cfg_gates.get('min_width', 100))
GATE_MIN_H = int(_cfg_gates.get('min_height', 80))
GATE_MIN_BRIGHT_PCT = float(_cfg_gates.get('min_bright_pct', 0.05))
GATE_MIN_BRIGHTNESS = float(_cfg_gates.get('min_mean_brightness', 30))
GATE_MIN_SATURATION = float(_cfg_gates.get('min_saturation', 20))

# Dedup quality ranking + review threshold from config
QUALITY_RANK = dict((CONFIG.get('dedup') or {}).get('quality_rank', {}) or
                    {'manual': 4, 'perfect': 3,
                     'needs_agent_review': 2, 'needs_human_review': 1})
REVIEW_THRESHOLD = int((CONFIG.get('review') or {}).get('accept_threshold', 90))


def get_files_for_date(target_date, cache_dir):
    """Find screenshot files for a specific date.

    Supports both the old Telega cache naming (*_121.jpg) and plain
    screenshots (*.jpg/*.png) in the configured screenshot directory.
    """
    target_str = target_date.strftime("%b %d")
    files = []
    for fname in sorted(os.listdir(cache_dir)):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        fpath = os.path.join(cache_dir, fname)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
        except OSError:
            continue
        if mtime.strftime("%b %d") == target_str:
            files.append((fpath, mtime))
    return sorted(files, key=lambda x: x[1])


def default_ledger_path():
    return os.path.join(repo_root(), "data", "extraction_status.yaml")


def load_ledger(path):
    """Load the per-screenshot status ledger ({filename: {...}})."""
    if yaml is not None and path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            shots = data.get("screenshots") or {}
            return shots if isinstance(shots, dict) else {}
        except Exception as e:
            print(f"  Warning: could not read ledger {path}: {e}")
    return {}


def save_ledger(path, shots):
    """Persist the ledger (crash-safe: write after every screenshot)."""
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ("# Extraction status ledger — managed by src/extract_quiz.py.\n"
              "# status: extracted | duplicate | skipped | failed.\n"
              "# Terminal statuses are not reprocessed unless --reprocess.\n")
    body = {"screenshots": shots}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(header)
        if yaml is not None:
            yaml.safe_dump(body, f, allow_unicode=True, sort_keys=True)
        else:
            f.write(repr(body))
    os.replace(tmp, path)


def load_known_titles(org_path):
    """Normalized question titles already in the org DB (dup check)."""
    titles = set()
    if org_path and os.path.exists(org_path):
        with open(org_path, encoding="utf-8") as f:
            text = f.read()
        for m in re.finditer(r"(?m)^\*\* (.+)$", text):
            titles.add(normalize_question(m.group(1).strip()))
    return titles


def ledger_record(shots, fname, status, data=None, reason=None):
    rec = {"status": status,
           "processed_at": datetime.now().isoformat(timespec="seconds")}
    if data:
        rec["question"] = data.get("question", "")
        rec["id"] = generate_id(data.get("question", fname))
        rec["correct"] = data.get("correct")
        rec["quality"] = "needs_agent_review"
    if reason:
        rec["reason"] = reason
    shots[fname] = rec
    return rec


def get_all_files(cache_dir):
    """All screenshots in a directory, oldest first."""
    files = []
    for fname in sorted(os.listdir(cache_dir)):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        fpath = os.path.join(cache_dir, fname)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
        except OSError:
            continue
        files.append((fpath, mtime))
    return sorted(files, key=lambda x: x[1])


def preprocess_for_ocr(img):
    """Preprocess image for better OCR."""
    large = img.resize((
        img.width * int(_cfg_ocr.get("resize_block", 3)),
        img.height * int(_cfg_ocr.get("resize_block", 3)),
    ), Image.LANCZOS)
    gray = large.convert('L')
    enh = ImageEnhance.Contrast(gray).enhance(
        float(_cfg_ocr.get("contrast", 2.5)))
    threshold = int(_cfg_ocr.get("threshold", 140))
    return enh.point(lambda x: 0 if x < threshold else 255, '1')


def ocr_region(img, bbox):
    """OCR a specific region of the image."""
    region = img.crop(bbox)
    processed = preprocess_for_ocr(region)
    lang = _cfg_ocr.get("lang", "rus+eng")
    psm = int(_cfg_ocr.get("psm_block", 6))
    text = pytesseract.image_to_string(
        processed, lang=lang, config=f'--psm {psm}')
    return text.strip()


def _ocr_candidate(image, lang, psm):
    data = pytesseract.image_to_data(
        image, lang=lang, config=f'--psm {psm}',
        output_type=pytesseract.Output.DICT)
    lines = {}
    confidences = []
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        if not text or not any(char.isalnum() for char in text):
            continue
        line = (
            data["block_num"][index],
            data["par_num"][index],
            data["line_num"][index],
        )
        lines.setdefault(line, []).append(text)
        try:
            confidence = float(data["conf"][index])
        except ValueError:
            continue
        if confidence >= 0:
            confidences.append(confidence)
    text = "\n".join(" ".join(words) for words in lines.values())
    confidence = sum(confidences) / len(confidences) if confidences else 0
    return text, confidence


def ocr_answer_quadrant(img, quadrant_num, quadrants=None):
    """OCR a specific answer quadrant with specialized preprocessing."""
    boxes = quadrants or LAYOUT['answer_quadrants']
    x1, y1, x2, y2 = boxes[quadrant_num]
    region = img.crop((x1, y1, x2, y2))

    scale = int(_cfg_ocr.get("resize_block", 3))
    contrast = float(_cfg_ocr.get("contrast", 2.5))
    threshold = int(_cfg_ocr.get("threshold", 140))
    lang = _cfg_ocr.get("lang", "rus+eng")
    psm_block = int(_cfg_ocr.get("psm_block", 6))
    thresholds = tuple(dict.fromkeys((
        max(60, threshold - 60),
        max(80, threshold - 40),
        max(80, threshold - 20),
        threshold,
    )))
    psms = tuple(dict.fromkeys((psm_block, 7, 8, 11)))

    best_text = ""
    best_score = 0

    for invert in (False, True):
        large = region.resize(
            (region.width * scale, region.height * scale), Image.LANCZOS)
        gray = large.convert('L')
        if invert:
            gray = ImageOps.invert(gray)

        enh = ImageEnhance.Contrast(gray).enhance(contrast)
        for thresh in thresholds:
            processed = enh.point(lambda x: 0 if x < thresh else 255, '1')
            for psm in psms:
                text, confidence = _ocr_candidate(processed, lang, psm)
                if text:
                    alphanumeric = sum(char.isalnum() for char in text)
                    punctuation = sum(
                        not char.isalnum() and not char.isspace()
                        for char in text)
                    score = confidence + alphanumeric - punctuation * 2
                    if score > best_score:
                        best_score = score
                        best_text = text

    # Clean up - return first meaningful line
    if best_text:
        lines = [l.strip() for l in best_text.split('\n') if l.strip() and len(l.strip()) > 2]
        for line in lines:
            if len(line) >= 3 and not line.startswith('@') and not all(c in '|=-.()[]{}' for c in line):
                return line
    
    return ""


def validate_category(ocr_text):
    """Validate OCR text against known categories by searching for them."""
    # Also try line by line
    for line in ocr_text.split('\n'):
        line_clean = re.sub(r'\d{1,2}:\d{2}', '', line)
        line_clean = line_clean.replace('@', '').replace('©', '').replace('®', '').replace('Ф', '')
        line_clean = line_clean.replace('|', '').replace('[', '').replace(']', '').strip()
        for cat in KNOWN_CATEGORIES:
            if cat.lower() in line_clean.lower():
                return cat
    return None


def extract_question_image(img):
    """Extract a photo from the screenshot's image card, excluding its header."""
    region = img.crop(QUESTION_IMAGE_REGION)
    if not has_question_image(region):
        return None
    return region.copy()


def has_question_image(img):
    """Reject text-only cards while retaining dark, colorful photos."""
    if img is None:
        return False
    if img.width < GATE_MIN_W or img.height < GATE_MIN_H:
        return False

    pixels = np.asarray(img.convert("RGB"), dtype=np.uint8)
    brightness = pixels.mean(axis=2)
    saturation = pixels.max(axis=2) - pixels.min(axis=2)
    bright_pct = float(np.mean(brightness > 100))
    mean_brightness = float(np.mean(brightness))
    avg_saturation = float(np.mean(saturation))

    return (
        bright_pct >= GATE_MIN_BRIGHT_PCT
        and mean_brightness >= GATE_MIN_BRIGHTNESS
        and avg_saturation >= GATE_MIN_SATURATION
    )


def detect_green_answer(img):
    """Detect correct answer by green highlight in answer quadrants."""
    green_counts = {}
    for q, (x1, y1, x2, y2) in LAYOUT['green_quadrants'].items():
        count = 0
        for y in range(y1, min(y2, img.height)):
            for x in range(x1, min(x2, img.width)):
                try:
                    pixel = img.getpixel((x, y))
                    if isinstance(pixel, tuple):
                        r, g, b = pixel[:3]
                        # Green detection thresholds come from config.yaml
                        if g > r + GREEN_DELTA and g > b + GREEN_DELTA and g > GREEN_MIN_G:
                            count += 1
                except:
                    pass
        green_counts[q] = count
    
    if green_counts:
        max_q = max(green_counts, key=green_counts.get)
        if green_counts[max_q] > GREEN_MIN_PIXELS:
            return max_q
    raise ValueError("No green highlight found - CORRECT cannot be empty!")


def extract_category(img):
    """Extract category by OCRing the full image and searching for known categories."""
    w, h = img.size
    
    if (w, h) != (LAYOUT['width'], LAYOUT['height']):
        print(f"  Skipping: size {w}x{h}px != layout size "
              f"{LAYOUT['width']}x{LAYOUT['height']}px "
              f"(needs a new layout profile, e.g. Cubot P60)")
        return None

    # OCR the entire image to find category names
    scale = int(_cfg_ocr.get("resize_full", 4))
    large = img.resize((w * scale, h * scale), Image.LANCZOS)
    gray = large.convert('L')
    contrast = float(_cfg_ocr.get("contrast", 2.5))
    threshold = int(_cfg_ocr.get("threshold", 140))
    lang = _cfg_ocr.get("lang", "rus+eng")
    psm = int(_cfg_ocr.get("psm_full", 3))
    
    # Try both normal and inverted
    for invert in [False, True]:
        if invert:
            gray = ImageOps.invert(gray)
        enh = ImageEnhance.Contrast(gray).enhance(contrast)
        processed = enh.point(lambda x: 0 if x < threshold else 255, '1')
        
        # Use the configured page-segmentation mode for the full image.
        text = pytesseract.image_to_string(
            processed, lang=lang, config=f'--psm {psm}')
        text = text.strip()
        
        if text:
            print(f"  DEBUG full image invert={invert}: '{text[:200]}'")
        
        # Search for known categories (with and without spaces)
        for cat in KNOWN_CATEGORIES:
            if cat.lower() in text.lower():
                return cat
            if cat.replace(' ', '').lower() in text.replace(' ', '').lower():
                return cat
    
    return None


def extract_full_question_text(img):
    """Extract full question text from the question area (y=280-580)."""
    w, h = img.size
    region = img.crop(LAYOUT['question_text_region'])
    
    # Preprocess for OCR
    scale = int(_cfg_ocr.get("resize_block", 3))
    large = region.resize(
        (region.width * scale, region.height * scale), Image.LANCZOS)
    gray = large.convert('L')
    enh = ImageEnhance.Contrast(gray).enhance(
        float(_cfg_ocr.get("contrast", 2.5)))
    threshold = int(_cfg_ocr.get("threshold", 140))
    processed = enh.point(lambda x: 0 if x < threshold else 255, '1')
    
    # PSM 6 for block of text
    lang = _cfg_ocr.get("lang", "rus+eng")
    psm = int(_cfg_ocr.get("psm_block", 6))
    text = pytesseract.image_to_string(
        processed, lang=lang, config=f'--psm {psm}')
    text = text.strip()
    
    if text:
        print(f"  DEBUG question: '{text[:100]}'")
    
    # Join multi-line question, stop before answers start
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 2]
    question_lines = []
    for line in lines:
        # Stop if line looks like an answer (short, no question mark)
        if '?' in line or len(line) > 15:
            question_lines.append(line)
        elif question_lines:
            break
    
    return ' '.join(question_lines) if question_lines else (lines[0] if lines else "Unknown question")


def extract_full_text(img):
    """Extract full text from image using best preprocessing."""
    w, h = img.size
    scale = int(_cfg_ocr.get("resize_full", 4))
    large = img.resize((w * scale, h * scale), Image.LANCZOS)
    gray = large.convert('L')
    contrast = float(_cfg_ocr.get("contrast", 2.5))
    threshold = int(_cfg_ocr.get("threshold", 140))
    thresholds = tuple(dict.fromkeys((max(80, threshold - 40), threshold)))
    lang = _cfg_ocr.get("lang", "rus+eng")
    psm_full = int(_cfg_ocr.get("psm_full", 3))
    psms = tuple(dict.fromkeys((psm_full, 6)))
    
    best_text = ""
    best_score = 0
    
    for invert in (False, True):
        if invert:
            source = ImageOps.invert(gray)
        else:
            source = gray

        enh = ImageEnhance.Contrast(source).enhance(contrast)
        for thresh in thresholds:
            processed = enh.point(lambda x: 0 if x < thresh else 255, '1')
            for psm in psms:
                text = pytesseract.image_to_string(
                    processed, lang=lang, config=f'--psm {psm}').strip()

                if text:
                    score = len(text)
                    if any(c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
                           for c in text.lower()):
                        score += 100
                    if score > best_score:
                        best_score = score
                        best_text = text
    
    return best_text


def split_concatenated_answers(text):
    """Split concatenated answers like 'Bentley Aston Martin Jaguar Rolls-Royce' into individual answers."""
    # Known answer patterns for splitting concatenated answers
    KNOWN_PATTERNS = [
        'Бентли', 'Астон Мартин', 'Джагуар', 'Роллс-ройс',
        'Зеленый', 'Синий', 'Красный', 'Желтый',
        'Эрмитаж', 'Ваза', 'Лувр', 'Прадо',
        'Немия', 'Элджернон', 'Чарли', 'Алиса',
        'Нвидиа', 'Амд', 'Интел', 'Арре',
        'Первая смерть Отто', 'Третий сон Генри', 'Четвертый сын Морти', 'Вторая жизнь Уве',
        'Синица', 'Дятел', 'Клест', 'Снегирь',
        'Джакомо Пуччини', 'Джузеппе Верди', 'Винченцо Беллини', 'Джоаккино Россини',
        'Много', 'Одно', 'Ни одного', 'Два',
        'Герберт Уэллс', 'Олдос Хаксли', 'Рэй Брэдбери', 'Джордж Оруэлл',
        'Джеймс Уатт', 'Исаак Ньютон', 'Альберт Эйнштейн', 'Михаил Ломоносов',
        'России', 'Испании', 'Италии', 'Китая',
        'VGA', 'OMG', 'DSL', 'MES', 'NFC', 'DSL',
        'Льюис Кэрролл', 'Макс Фрай', 'Роберт Гэлбрейт', 'Агата Кристи',
        'Михаил Ломоносов', 'Томас Эдисон', 'Никола Тесла', 'Бенджамин Франклин',
        'Тжвжик', 'Чахохбили', 'Хинкали', 'Хачапури',
        'Коллапсар', 'Горизонт событий', 'Фотонная сфера', 'Оболочка',
        'Льва', 'Орла', 'Быка', 'Медведя',
    ]
    
    # Try to match known answers in text
    found = []
    text_lower = text.lower()
    for pattern in KNOWN_PATTERNS:
        if pattern.lower() in text_lower:
            found.append(pattern)
    
    if len(found) >= 2:
        return found[:4]
    
    # Fallback: split on common separators
    # Split on capitalized words that look like answer boundaries
    import re
    # Try to split on patterns like "Word1 Word2 | Word3 Word4" or "Word1Word2Word3"
    # Split on " | " or "  " (double space) or capital letter followed by lowercase
    parts = re.split(r'\s*\|\s*|\s{2,}', text)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
    if len(parts) >= 2:
        return parts[:4]
    
    # Fallback: return as single
    return [text]


def parse_quiz_from_text(text):
    """Parse category, question, and 4 answers from full image OCR text."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Find category
    category = None
    for line in lines:
        for cat in KNOWN_CATEGORIES:
            if cat.lower() in line.lower():
                category = cat
                break
        if category:
            break
    
    # Find question - look for line with ? that's the actual question
    question = None
    question_idx = -1
    for i, line in enumerate(lines):
        if '?' in line and len(line) > 15:
            # Skip if it's a footer line
            lower = line.lower()
            if not any(kw in lower for kw in ['продолжить', 'верно', 'следующ', '@ верно', 'неверно', 'другой вопрос', 'сдаться']):
                question = line
                question_idx = i
                break
    
    if not question:
        # Fallback: any line with ?
        for i, line in enumerate(lines):
            if '?' in line and len(line) > 10:
                lower = line.lower()
                if not any(kw in lower for kw in ['продолжить', 'верно', 'следующ', '@ верно', 'неверно', 'другой вопрос', 'сдаться']):
                    question = line
                    question_idx = i
                    break
    
    if not question:
        return category, "Unknown question", {}

    question = re.sub(r"^.*?\b\d{1,2}:\d{2}\s+", "", question)

    # Remove category prefix from question if present
    if category and question.lower().startswith(category.lower()):
        question = question[len(category):].strip()
        question = question.lstrip(' .,:;|-')
    
    # Category on the previous OCR line: the question itself is already
    # clean — just tidy leading separators, never chop characters.
    if category and question_idx > 0 and category.lower() in lines[question_idx - 1].lower():
        question = question.lstrip(' .,:;|-')
    
    # Also handle case where category is anywhere in question (not just start)
    if category:
        q_lower = question.lower()
        cat_lower = category.lower()
        if cat_lower in q_lower:
            # Find and remove the category from anywhere in the question
            idx = q_lower.find(cat_lower)
            question = question[:idx] + question[idx + len(category):]
            question = question.strip()
            question = question.lstrip(' .,:;|-')
    
    # Build complete question - include preceding lines if they're part of question
    if question_idx > 0:
        for j in range(question_idx - 1, -1, -1):
            prev_line = lines[j]
            if len(prev_line) > 10 and '?' not in prev_line:
                question = prev_line + ' ' + question
            else:
                break
    question = re.sub(r"^.*?\b\d{1,2}:\d{2}\s+", "", question)

    # Strip the category again AFTER prepending: the category often sits on
    # its own OCR line above the question and would otherwise leak back in.
    if category:
        q_lower = question.lower()
        cat_lower = category.lower()
        if cat_lower in q_lower:
            idx = q_lower.find(cat_lower)
            question = question[:idx] + question[idx + len(category):]
            question = question.strip().lstrip(' .,:;|-')
        question = re.sub(r'\s+', ' ', question).strip()
    
    # Extract answers from lines after question
    answers = {}
    if question_idx >= 0:
        answer_candidates = []
        for line in lines[question_idx + 1:]:
            lower = line.lower()
            if any(kw in lower for kw in ['продолжить', 'верно', 'следующ', '@ верно', 'неверно', 'другой вопрос', 'сдаться', 'следующий вопрос']):
                continue
            if re.match(r'^\d{1,2}:\d{2}', line):
                continue
            if line.startswith('@') or '©' in line or 'Ф' in line or '®' in line:
                continue
            if line.startswith('|'):
                continue
            if any(cat.lower() in line.lower() for cat in KNOWN_CATEGORIES):
                continue
            if re.match(r'^\d{2}:\d{2}', line):
                continue
            if line.startswith('<') or line.startswith('=') or line.startswith('>') or line.startswith('='):
                continue
            if line.startswith('-') or line.startswith('x'):
                continue
            
            clean = line.strip()
            if len(clean) > 2:
                answer_candidates.append(clean)
        
        # Process candidates - split concatenated answers
        processed = []
        for cand in answer_candidates:
            parts = split_concatenated_answers(cand)
            for p in parts:
                if len(p) > 2 and not p.startswith('<') and not p.startswith('=') and not p.startswith('>') and not p.startswith('@'):
                    processed.append(p)
        
        # Deduplicate while preserving order - also remove partial duplicates
        seen = set()
        unique_processed = []
        for p in processed:
            # Skip if this is a substring of another answer or vice versa
            is_dup = False
            for existing in unique_processed:
                if p in existing or existing in p:
                    is_dup = True
                    break
            if not is_dup and p not in seen:
                seen.add(p)
                unique_processed.append(p)
        
        # Take first 4 valid answers
        for i, ans in enumerate(unique_processed[:4]):
            answers[i + 1] = ans
    
    # If we have fewer than 4 answers, try to extract from full text after question
    if len(answers) < 4 and question_idx >= 0:
        full_after_question = text[text.find(question) + len(question):]
        for pattern in KNOWN_PATTERNS:
            if pattern.lower() in full_after_question.lower() and pattern not in answers.values():
                for i in range(1, 5):
                    if i not in answers:
                        answers[i] = pattern
                        break
    
    return category, question, answers


def extract_quiz_data(img):
    """Extract all quiz data from a screenshot using per-region OCR."""
    w, h = img.size
    
    # Skip images whose width does not match the configured layout
    # (e.g. future Cubot P60 native screenshots need their own profile)
    if (w, h) != (LAYOUT['width'], LAYOUT['height']):
        print(f"  Skipping: size {w}x{h}px != layout size "
              f"{LAYOUT['width']}x{LAYOUT['height']}px")
        return None
    
    # Get full image text for category and question
    full_text = extract_full_text(img)
    if not full_text:
        print("  Could not extract text")
        return None
    
    print(f"  DEBUG full text: '{full_text[:200]}'")
    
    # Parse category and question from full text
    category, question, _ = parse_quiz_from_text(full_text)
    
    if not category:
        print(f"  Warning: Unknown category from OCR")
        return None
    print(f"  Category: {category}")
    
    if not question or question == "Unknown question":
        print("  Could not extract question")
        return None
    print(f"  Question: {question[:80]}...")

    question_img = extract_question_image(img)
    answer_regions = (
        LAYOUT['answer_quadrants_with_image']
        if question_img is not None else LAYOUT['answer_quadrants']
    )
    
    # Extract answers using per-quadrant OCR with inverted preprocessing
    answers = {}
    for q in range(1, 5):
        ans_text = ocr_answer_quadrant(img, q, answer_regions)
        if ans_text:
            # Clean up the answer text
            ans_text = ans_text.strip()
            # Remove common OCR artifacts
            ans_text = ans_text.replace('|', '').strip()
            answers[q] = ans_text
            print(f"  Answer {q}: {ans_text}")
        else:
            answers[q] = f"[Answer {q} not found]"
            print(f"  Answer {q}: [not found]")
    
    # Ensure we have 4 answers
    for i in range(1, 5):
        if i not in answers or not answers[i]:
            answers[i] = f"[Answer {i} not found]"
    
    print(f"  Answers: {answers}")
    
    # Detect correct answer (MUST succeed)
    correct = detect_green_answer(img)
    print(f"  Correct: {correct}")
    
    return {
        'category': category,
        'question': question,
        'answers': answers,
        'correct': correct,
        'question_image': question_img
    }


def slugify(text):
    """Create a short slug from TEXT (ported from convert-robust.el logic)."""
    raw = text.lower().strip()
    one = re.sub(r"[\s\n\r\t]+", " ", raw)
    slug = re.sub(r"[^0-9a-zа-яё-]+", "-", one)
    slug = re.sub(r"^-+|-+$", "", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:40]


def generate_id(text):
    """Generate unique ID from text: slug + '-' + 8-char sha1."""
    return slugify(text) + "-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def normalize_question(text):
    """Normalized form used for duplicate comparison."""
    t = text.lower().replace("ё", "е")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[«»\"'?!.,:;—–-]+", "", t).strip()
    return t


def is_entry_broken(data):
    """True when OCR clearly failed (placeholder answers / empty fields)."""
    answers = data.get("answers", {})
    if len([a for a in answers.values() if a and "not found]" not in str(a)]) < 4:
        return True
    if not data.get("category") or not data.get("question"):
        return True
    if not data.get("correct"):
        return True
    return False


def append_to_org(data, img_path=None, org_file=DEFAULT_ORG_FILE, quality=None):
    """Append quiz entry to org file.

    Always writes :ID: and :EXTRACTION_QUALITY:.
    New automatic extractions default to needs_agent_review: agents keep
    improving them until they score well or give up and escalate the
    entry to needs_human_review.
    """
    if quality is None:
        quality = "needs_agent_review"
    with open(org_file, 'a', encoding='utf-8') as f:
        f.write(f"\n** {data['question']}\n")
        f.write(":PROPERTIES:\n")
        f.write(f":ID:       {generate_id(data['question'])}\n")
        f.write(f":CATEGORY:   {data['category']}\n")
        for i in range(1, 5):
            ans = data['answers'].get(i, "")
            f.write(f":ANSWER{i}:    {ans}\n")
        f.write(f":CORRECT:    {data['correct']}\n")
        if img_path:
            f.write(f":IMAGE_LINK: {img_path}\n")
        else:
            f.write(":IMAGE_LINK: nil\n")
        f.write(f":EXTRACTION_QUALITY: {quality}\n")
        f.write(":END:\n\n")


def main():
    parser = argparse.ArgumentParser(description="Extract quiz questions from screenshots (config.yaml driven)")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD), default: yesterday")
    parser.add_argument("--all", action="store_true", help="Process all screenshots in --dir, not just one date")
    parser.add_argument("--dir", type=str, default=DEFAULT_CACHE_DIR, help="Screenshot directory")
    parser.add_argument("--org", type=str, default=DEFAULT_ORG_FILE, help="Org file path")
    parser.add_argument("--img-dir", type=str, default=DEFAULT_IMG_DIR, help="Images output directory")
    parser.add_argument("--status", type=str, default=None,
                        help="Status ledger path (default: data/extraction_status.yaml)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process at most N new screenshots (0 = no limit)")
    parser.add_argument("--reprocess", action="store_true",
                        help="Reprocess screenshots already in the ledger")
    args = parser.parse_args()

    global CONFIG, _cfg_ocr
    if args.config:
        os.environ["QUIZY_CONFIG"] = args.config
        CONFIG = load_config(args.config)
        _cfg_ocr = CONFIG.get("ocr") or {}

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)

    os.makedirs(args.img_dir, exist_ok=True)

    ledger_path = args.status or default_ledger_path()
    shots = load_ledger(ledger_path)
    known_titles = load_known_titles(args.org)
    print(f"Ledger: {len(shots)} screenshots recorded, "
          f"{len(known_titles)} questions in DB.")

    if args.all:
        files = get_all_files(args.dir)
        print(f"Found {len(files)} screenshots in {args.dir}")
    else:
        files = get_files_for_date(target_date, args.dir)
        print(f"Found {len(files)} screenshots for {target_date.strftime('%Y-%m-%d')}")

    processed = 0
    skipped = 0
    already_done = 0
    duplicates = 0

    for fpath, mtime in files:
        fname = os.path.basename(fpath)
        prev = shots.get(fname)
        if prev and prev.get("status") in (
                "extracted", "duplicate", "skipped", "failed") \
                and not args.reprocess:
            already_done += 1
            continue
        if args.limit and (processed + skipped + duplicates) >= args.limit:
            print(f"  Limit reached ({args.limit}); stopping.")
            break
        print(f"\nProcessing: {fname}")
        try:
            img = Image.open(fpath)
            data = extract_quiz_data(img)

            if not data or data['question'] == "Unknown question":
                print("  Skipping: Could not extract question")
                ledger_record(shots, fname, "skipped",
                              reason="no question/category extracted")
                save_ledger(ledger_path, shots)
                skipped += 1
                continue

            print(f"  Category: {data['category']}")
            print(f"  Question: {data['question'][:80]}...")
            print(f"  Answers: {data['answers']}")
            print(f"  Correct: {data['correct']}")

            # Duplicate vs DB? Record and move on — never append twice.
            if normalize_question(data['question']) in known_titles:
                print("  Duplicate of existing DB entry — not appended")
                ledger_record(shots, fname, "duplicate", data,
                              reason="question already in org DB")
                save_ledger(ledger_path, shots)
                duplicates += 1
                continue

            # Save question image if exists
            img_link = None
            if data['question_image'] and has_question_image(data['question_image']):
                qid = generate_id(data['question'])
                img_name = f"qimg_real_{qid}.jpg"
                img_save_path = os.path.join(args.img_dir, img_name)
                data['question_image'].save(img_save_path)
                img_link = f"./images/{img_name}"
                print(f"  Saved image: {img_name}")

            append_to_org(data, img_link, args.org)
            known_titles.add(normalize_question(data['question']))
            ledger_record(shots, fname, "extracted", data)
            save_ledger(ledger_path, shots)
            print("  Added to org file")
            processed += 1

        except ValueError as e:
            if "CORRECT cannot be empty" in str(e):
                print(f"  Skipping: {e}")
                ledger_record(shots, fname, "failed", reason=str(e))
                save_ledger(ledger_path, shots)
                skipped += 1
            else:
                print(f"  Error: {e}")
                ledger_record(shots, fname, "failed", reason=str(e))
                save_ledger(ledger_path, shots)
                skipped += 1
        except Exception as e:
            print(f"  Error: {e}")
            ledger_record(shots, fname, "failed", reason=str(e))
            save_ledger(ledger_path, shots)
            skipped += 1

    print(f"\nDone! New: {processed}, Duplicates: {duplicates}, "
          f"Skipped/failed: {skipped}, Already recorded: {already_done}")


if __name__ == "__main__":
    main()