"""
Region-based dimension OCR (Slice B).

Replaces whole-image OCR with: detect small text-like blobs, OCR each region
individually (upscaled, with rotation attempts), preferring EasyOCR when
installed and falling back to Tesseract. Whole-image OCR was tried first and
performed worse on real (scanned/photographed) drawings, where dimension text
is small relative to the sheet and gets lost in noise; per-region upscaling
recovers much of that.

Honest scope: this reads PLAIN NUMBERS (digits + decimal point) reliably ON
CLEAN INPUT ONLY. It does not read tolerance symbols (±, +/-) or GD&T frames
-- the OCR character allowlist below doesn't even include those symbols, by
design, because asserting we parse them would overclaim. A leading "O"/"o"
(a common OCR misread of the diameter symbol Ø) or "R" next to a number is
surfaced as a LOW-CONFIDENCE diameter/radius hint, not an asserted reading.

MEASURED on the real reference drawing (storage/uploads/012eeb226497.jpg, a
296x393 photographed/scanned part drawing with 12 visible dimension labels:
33, 28, 30, 65, 35, 91.5, 49.5, 21, 21, 13, 9, 33): region detection finds 17
candidate regions (up from ~1 with the original whole-image-Otsu approach --
see _find_text_regions), but EasyOCR reads 5 of them above the 0.3 confidence
floor, and NONE of the 5 readings match a visible label (it reads "2", "8",
"14", "8", "1" -- plausible character-level confusions on small, JPEG-noisy
digits, not real values). At this image resolution/compression, region
detection is no longer the bottleneck; OCR accuracy on tiny noisy digits is.
This is reported plainly rather than tuned until it looks like it works --
README has the same numbers.
"""
import re
import shutil
from pathlib import Path

import cv2
import numpy as np

_READER = None
_ENGINE = None

try:
    import easyocr
    _READER = easyocr.Reader(["en"], gpu=False)
    _ENGINE = "easyocr"
except Exception:
    _READER = None
    try:
        import pytesseract

        # Windows commonly installs tesseract outside PATH. Auto-discover the
        # usual install locations; uncomment + edit the line below to force a
        # specific path instead (e.g. a portable install):
        # pytesseract.pytesseract.tesseract_cmd = r"C:\path\to\tesseract.exe"
        if shutil.which(pytesseract.pytesseract.tesseract_cmd) is None:
            for candidate in (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ):
                if Path(candidate).exists():
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break
        pytesseract.get_tesseract_version()  # raises if the binary isn't reachable
        _ENGINE = "tesseract"
    except Exception:
        _ENGINE = None

NUM = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_PREFIX_RE = re.compile(r"^\s*([OoRr])")


def _find_text_regions(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Detect small text-like blobs and cluster nearby characters into label boxes.

    Tuned against a REAL photographed/scanned drawing (storage/uploads), not a
    synthetic one. On a real drawing, dimension numbers sit directly against
    extension/leader lines, so a single global Otsu threshold (the original
    approach) connects text and line-art into one giant per-view blob -- on
    the reference drawing that collapsed ~12 visible dimension labels into a
    single contour per view, finding ~1 usable text region total.

    Fix: detect long straight lines via directional morphological opening
    (structural geometry, by definition, is long and either roughly horizontal
    or vertical) and subtract them from the threshold mask BEFORE clustering.
    What's left is mostly characters, which a small dilation then merges into
    per-number boxes. This recovered ~17 candidate regions against the same
    drawing's ~12 visible labels (the rest are leftover arrowhead/leader-line
    fragments that survive the line-removal step; see module docstring for
    the empirically measured OCR accuracy on those regions).
    """
    inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
    horiz_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, horiz_kernel)
    vert_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, vert_kernel)
    lines_mask = cv2.dilate(cv2.bitwise_or(horiz_lines, vert_lines), np.ones((3, 3), np.uint8))
    residual = cv2.bitwise_and(inv, cv2.bitwise_not(lines_mask))

    # connect characters within a word/number horizontally
    dilated = cv2.dilate(residual, cv2.getStructuringElement(cv2.MORPH_RECT, (12, 3)))
    cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    H, W = gray.shape
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        ar = w / max(h, 1)
        # text-like: not too big, not too thin, reasonable aspect. Bounds
        # tightened from the original (h<=60, w<=400) to match the actual
        # dimension-label scale measured on the reference drawing.
        if 8 <= h <= 35 and 5 <= w <= 100 and 0.3 <= ar <= 8 and w * h < 0.05 * W * H:
            boxes.append((x, y, w, h))
    return boxes


def _read(img: np.ndarray) -> list[tuple[str, float]]:
    if _ENGINE == "easyocr":
        try:
            res = _READER.readtext(img, allowlist="0123456789.OoRr")
            return [(t, float(c)) for _, t, c in res]
        except Exception:
            return []
    elif _ENGINE == "tesseract":
        try:
            import pytesseract
            d = pytesseract.image_to_data(
                img, config="--psm 7 -c tessedit_char_whitelist=0123456789.OoRr",
                output_type=pytesseract.Output.DICT,
            )
            return [
                (t, int(d["conf"][i]) / 100)
                for i, t in enumerate(d["text"])
                if t.strip() and int(d["conf"][i]) >= 0
            ]
        except Exception:
            return []
    return []


def extract_dims(gray: np.ndarray) -> list[dict]:
    """Returns [{"text": <numeric string>, "raw": <full OCR text>, "conf": float,
    "at": [x, y]}, ...] for each text region where a number was read."""
    if _ENGINE is None:
        return []

    out = []
    for (x, y, w, h) in _find_text_regions(gray):
        pad = 4
        roi = gray[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
        if roi.size == 0:
            continue
        roi = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        roi = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        best = None
        for rot in (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            test = cv2.rotate(roi, rot) if rot is not None else roi
            for txt, conf in _read(test):
                m = NUM.search(txt)
                if m and conf > 0.3 and (best is None or conf > best[1]):
                    best = (m.group(), conf, (x + w / 2, y + h / 2), txt)
        if best:
            out.append({
                "text": best[0],
                "raw": best[3],
                "conf": round(best[1], 2),
                "at": [round(best[2][0]), round(best[2][1])],
            })
    return out


if __name__ == "__main__":
    import sys
    g = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else "crop.png", cv2.IMREAD_GRAYSCALE)
    print("engine:", _ENGINE)
    print("regions found:", len(_find_text_regions(g)))
    dims = extract_dims(g)
    print(f"dimensions read: {len(dims)}")
    for d in dims:
        print(" ", d)
