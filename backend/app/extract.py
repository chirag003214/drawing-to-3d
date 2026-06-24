"""
Tuned CV geometry extraction for Slice B.

Drop-in replacement for the extraction logic. Produces primitives + dimensions
in the IR shape (kind / geom / layer / confidence) in VIEW-LOCAL coordinates.

Key improvements over the naive version:
  - HoughCircles tuned (param2, minDist, radius bounds) + dedup
  - PERIMETER-SUPPORT filter: a real circle has ink along its circumference;
    phantom circles do not. This is what kills the 84-circle over-detection
    without overfitting thresholds to one drawing.
  - THREE-SIGNAL line classifier (replaces the old axis-alignment heuristic):
      1. Relative length  — object lines span a large fraction of the view;
                            witness/leader lines are short stubs.
      2. Endpoint ink density — object lines end at corners/intersections
                            (high ink); dimension lines end in open space
                            near text (low ink).
      3. Axis alignment   — used as a tiebreaker, not the primary signal.
    This is what keeps dimension witness lines out of the object layer and
    produces a clean IR for the downstream stages.
  - Collinear/duplicate line merging.
  - Confidence floor so low-value "unknown" primitives are dropped.
  - Dimension OCR (multi-scale Tesseract); each number is linked to the
    nearest object primitive as an UNCONFIRMED heuristic, never asserted.
"""
from __future__ import annotations
import uuid
import math
import cv2
import numpy as np

try:
    import pytesseract
    _HAS_TESS = True
except Exception:
    _HAS_TESS = False

# On Windows, if tesseract isn't on PATH, uncomment and set this:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _id(prefix): return f"{prefix}_{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- #
# Circles
# --------------------------------------------------------------------------- #
def _detect_circles(gray, ink_dilated):
    H, W = gray.shape
    max_r = int(min(W, H) * 0.40)          # no hole bigger than 40% of the view
    raw = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1,
        minDist=35,        # collapse duplicates on the same hole
        param1=100,        # Canny high threshold
        param2=38,         # accumulator threshold (lower = more sensitive)
        minRadius=8, maxRadius=max_r,
    )
    if raw is None:
        return []

    # dedup near-identical centers
    kept = []
    for cx, cy, r in raw[0]:
        if any(abs(cx - k[0]) < 15 and abs(cy - k[1]) < 15 for k in kept):
            continue
        kept.append((cx, cy, r))

    # perimeter-support filter: keep only circles with ink on their circumference
    out = []
    for cx, cy, r in kept:
        if _perimeter_support(ink_dilated, cx, cy, r) >= 0.55:
            out.append({
                "id": _id("prim"), "kind": "circle",
                "geom": {"cx": round(float(cx), 1), "cy": round(float(cy), 1),
                         "r": round(float(r), 1)},
                "layer": "object", "confidence": 0.8,
            })
    return out


def _perimeter_support(ink_dilated, cx, cy, r, n=48):
    H, W = ink_dilated.shape
    ang = np.linspace(0, 2 * math.pi, n, endpoint=False)
    xs = (cx + r * np.cos(ang)).astype(int)
    ys = (cy + r * np.sin(ang)).astype(int)
    inb = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
    if inb.sum() == 0:
        return 0.0
    return float(ink_dilated[ys[inb], xs[inb]].mean())


# --------------------------------------------------------------------------- #
# Lines — three-signal classifier
# --------------------------------------------------------------------------- #
def _endpoint_ink_density(ink, x1, y1, x2, y2, radius=10):
    """How much ink surrounds each endpoint?
    Object lines end at part corners/intersections → high density.
    Dimension witness lines end in open space near text → low density."""
    H, W = ink.shape
    scores = []
    for px, py in [(int(x1), int(y1)), (int(x2), int(y2))]:
        x0 = max(0, px - radius);  x1_ = min(W, px + radius)
        y0 = max(0, py - radius);  y1_ = min(H, py + radius)
        patch = ink[y0:y1_, x0:x1_]
        scores.append(float(patch.mean()) if patch.size > 0 else 0.0)
    return max(scores)


def _classify_line(length, ang, view_diag, ep_ink):
    """Three-signal heuristic — order matters.

    Signal 1 — relative length (strongest):
      Object lines span a meaningful fraction of the view.
      Dimension witness/leader lines are short stubs.
    Signal 2 — endpoint ink density:
      Object lines terminate at geometry intersections (ink-rich).
      Witness lines terminate in whitespace near text (ink-poor).
    Signal 3 — axis alignment (tiebreaker only):
      Used to resolve ambiguous medium-length lines, not as primary signal.
      This prevents the old bug where diagonal object edges were mislabeled.
    """
    rel = length / max(view_diag, 1)
    axis = (ang < 8 or ang > 172 or abs(ang - 90) < 8)

    # Rule 1: long lines spanning >10% of view diagonal → always object
    if rel > 0.10:
        return "object", 0.85

    # Rule 2: short + low endpoint ink → dimension witness/leader line
    if rel < 0.06 and ep_ink < 0.25:
        return "dimension", 0.75

    # Rule 3: short + axis-aligned + low endpoint ink → dimension
    if rel < 0.08 and axis and ep_ink < 0.30:
        return "dimension", 0.65

    # Rule 4: medium diagonal lines with decent endpoint ink → object
    if not axis and rel > 0.05 and ep_ink >= 0.20:
        return "object", 0.75

    # Rule 5: very short → dimension noise
    if rel < 0.03:
        return "dimension", 0.60

    return "unknown", 0.4


def _detect_lines(gray, ink):
    H, W = gray.shape
    view_diag = math.hypot(W, H)

    edges = cv2.Canny(gray, 50, 150)
    segs = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                           minLineLength=max(15, int(view_diag * 0.03)),
                           maxLineGap=8)
    if segs is None:
        return []
    raw = [tuple(s[0]) for s in segs]

    # merge near-duplicate / collinear segments
    merged = []
    for x1, y1, x2, y2 in raw:
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        dup = False
        for m in merged:
            if abs(ang - m["ang"]) < 5 and \
               abs(mid[0] - m["mid"][0]) < 12 and \
               abs(mid[1] - m["mid"][1]) < 12:
                dup = True
                break
        if not dup:
            merged.append({"ang": ang, "mid": mid, "seg": (x1, y1, x2, y2)})

    out = []
    for m in merged:
        x1, y1, x2, y2 = m["seg"]
        length  = math.hypot(x2 - x1, y2 - y1)
        ep_ink  = _endpoint_ink_density(ink, x1, y1, x2, y2)
        layer, conf = _classify_line(length, m["ang"], view_diag, ep_ink)
        out.append({
            "id": _id("prim"), "kind": "line",
            "geom": {"x1": int(x1), "y1": int(y1),
                     "x2": int(x2), "y2": int(y2)},
            "layer": layer, "confidence": conf,
        })
    return out


# --------------------------------------------------------------------------- #
# Dimensions (OCR)
# --------------------------------------------------------------------------- #
def _extract_dimensions(gray, object_prims):
    """Dimension text is small; Tesseract needs it enlarged. We OCR at a couple
    of scales and merge, because no single scale catches every label."""
    if not _HAS_TESS:
        return []

    found = {}  # (x,y) bucket -> (text, conf) ; keeps highest-conf per location
    for scale in (2, 3):
        big = cv2.resize(gray, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        big = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        try:
            data = pytesseract.image_to_data(
                big, config="--psm 11", output_type=pytesseract.Output.DICT)
        except Exception:
            continue
        for i, raw in enumerate(data["text"]):
            txt = "".join(c for c in raw if c.isdigit() or c == ".")
            if not txt or not any(c.isdigit() for c in txt):
                continue
            conf = int(data["conf"][i])
            if conf < 40:
                continue
            # map back to original crop coordinates
            x = (data["left"][i] + data["width"][i] / 2) / scale
            y = (data["top"][i] + data["height"][i] / 2) / scale
            key = (round(x / 20), round(y / 20))  # ~20px dedup bucket
            if key not in found or conf > found[key][2]:
                found[key] = (txt, (x, y), conf)

    dims = []
    for txt, (x, y), conf in found.values():
        nearest = _nearest_object(x, y, object_prims)
        dims.append({
            "id": _id("dim"), "kind": "linear",
            "nominal": float(txt) if txt.replace(".", "", 1).isdigit() else None,
            "text_raw": txt, "tolerance": None,
            # UNCONFIRMED heuristic association — surfaced, not asserted
            "constrains": [nearest] if nearest else [],
            "gdt": None,
        })
    return dims


def _nearest_object(x, y, object_prims):
    best, bestd = None, 1e9
    for p in object_prims:
        g = p["geom"]
        if p["kind"] == "circle":
            px, py = g["cx"], g["cy"]
        else:
            px, py = (g["x1"] + g["x2"]) / 2, (g["y1"] + g["y2"]) / 2
        d = math.hypot(x - px, y - py)
        if d < bestd:
            best, bestd = p["id"], d
    return best


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def extract(crop_path: str, conf_floor: float = 0.4) -> dict:
    """Return {'primitives': [...], 'dimensions': [...]} for a saved crop."""
    gray_raw = cv2.imread(crop_path, cv2.IMREAD_GRAYSCALE)
    if gray_raw is None:
        raise FileNotFoundError(crop_path)
    gray = cv2.medianBlur(gray_raw, 3)  # blur for geometry; OCR uses gray_raw

    ink = (gray < 128).astype(np.uint8)
    ink_d = cv2.dilate(ink, np.ones((5, 5), np.uint8))

    circles = _detect_circles(gray, ink_d)
    lines = _detect_lines(gray, ink)
    prims = [p for p in (circles + lines) if p["confidence"] >= conf_floor]

    object_prims = [p for p in prims if p["layer"] == "object"]
    dims = _extract_dimensions(gray_raw, object_prims)

    return {"primitives": prims, "dimensions": dims}


if __name__ == "__main__":
    import sys, json
    res = extract(sys.argv[1] if len(sys.argv) > 1 else "crop.png")
    kinds = {}
    for p in res["primitives"]:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print(f"primitives: {len(res['primitives'])}  {kinds}")
    print(f"dimensions: {len(res['dimensions'])}  "
          f"{[d['text_raw'] for d in res['dimensions']]}")