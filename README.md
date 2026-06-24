# Drawing-to-3D Reconstruction Interface

Turns a 2D engineering drawing into a structured, tolerance-aware
representation that can drive 3D reconstruction. The graded deliverable is the
**intermediate representation (IR)** — extracted geometry linked to its
dimension and GD&T information — not the 3D render.

See `DESIGN.md` for the full architecture and the stages that are designed but
not built.

## Current status

| Component | State |
|-----------|-------|
| IR data model (`backend/app/models.py`) | **Built** |
| Storage + seed/contract test (`backend/seed.py`) | **Built** |
| Slice A — lasso crop, label & store (backend + frontend) | **Built** |
| Slice B — CV geometry extraction (backend + frontend) | **Built** |
| Frontend (React + canvas) | **Built** |
| Dimension text OCR (`app/ocr_dims.py`, EasyOCR preferred / Tesseract fallback) | **Built, low accuracy on the real test drawing** — see below |
| GD&T symbol recognition, multi-model router, stitching, 3D reconciliation, CAD viewer | Designed-not-built (see DESIGN.md) |

One continuous path runs end-to-end through the browser: upload a drawing →
lasso a view → label & store it → run CV extraction on that crop → inspect the
geometry overlay and the raw IR for that view.

## Repository layout

```
backend/
  app/
    models.py     # the IR: Drawing / View / Primitive / Dimension
                  #         + Correspondence / Feature3D (later stages)
    db.py         # SQLite engine + session + init_db()
    storage.py    # filesystem media store (uploads/crops/masks) — IR holds only URIs
    lasso.py       # server-side polygon -> mask -> crop (Slice A)
    extract.py     # CV geometry extraction (Slice B); calls ocr_dims for dimensions
    ocr_dims.py    # region-based dimension OCR: detect text regions, OCR each
                  #   individually (upscaled, rotation attempts); EasyOCR preferred,
                  #   Tesseract fallback
    schemas.py     # Pydantic request/response models
    main.py        # FastAPI app wiring endpoints to the IR
  seed.py         # inserts a full IR tree and asserts the cross-links resolve
  requirements.txt
frontend/         # React + Vite + canvas UI (Slice A) and SVG overlay (Slice B)
storage/
  uploads/  crops/  masks/   # raw image bytes; the IR stores only their paths
DESIGN.md
```

## Run it

**Backend** (from `backend/`):

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8077 --reload
```

**Frontend** (from `frontend/`):

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend talks to the backend at
`http://127.0.0.1:8077` (hardcoded in `frontend/src/api.js` for local dev — no
build-time config needed for this scope).

## Run the IR contract test

```bash
cd backend
pip install -r requirements.txt
python seed.py
```

Expected output: three `PASS` lines, a printed IR tree, and
`ALL CONTRACT CHECKS PASSED`. The test proves the IR can express the round-trip
the task cares about — from a reconstructed 3D feature back to the 2D geometry
and the **tolerance** that governs it. Note: stop the FastAPI server first if
it's running — SQLite on Windows holds an exclusive file lock and `seed.py`
resets the DB file.

## What the IR encodes (and why)

- **`Primitive.geom`** is stored in **view-local coordinates** — geometry is
  scoped to the view it came from, so stitching can place views independently.
- **`Dimension.constrains -> [primitive_id]`** links each measurement to the
  geometry it sizes. This is what makes the representation tolerance-aware.
- **`Feature3D.provenance -> {primitives, dimensions}`** links each 3D feature
  back to the 2D primitives and tolerances that produced it — the trace needed
  by downstream manufacturing process planning.

## What works

- **Upload** (`POST /drawings`): saves the image to `storage/uploads/`, creates
  a `Drawing` row, returns its true pixel dimensions.
- **Lasso, crop, label** (`POST /drawings/{id}/views`): the frontend canvas
  captures a freehand polygon in canvas-display coordinates; the backend scales
  it to true image pixels, rasterizes the mask with `cv2.fillPoly`, crops to
  the bounding box, and makes everything outside the polygon transparent. The
  crop+mask are saved to `storage/crops/` and `storage/masks/`; a `View` row is
  created with `crop_uri`/`mask_uri`. All pixel math is server-side, as required.
- **CV extraction** (`POST /views/{id}/extract`): runs on the saved crop —
  grayscale → `HoughCircles` (tuned `param2`/`minDist`/radius bounds) with a
  perimeter-support filter (a real circle has ink along its circumference;
  phantom detections don't) and center dedup → `HoughLinesP` for line
  segments, merged for near-duplicates/collinearity, then classified into
  object/dimension/unknown layers. Line layer classification uses a
  three-signal heuristic (relative length, endpoint ink density, axis
  alignment). Object lines and dimension witness lines are now separated in
  the IR. Diagonal object edges are correctly labeled regardless of angle.
  Drops low-confidence "unknown" primitives before writing to the IR. Writes
  real `Primitive` rows (view-local coordinates) and returns an SVG overlay.
  Re-running extraction replaces prior primitives rather than accumulating
  duplicates. Dimension OCR is a separate stage — see below.
- **Frontend**: upload, live freehand lasso capture (mouse + touch), label
  dropdown, notes field, a saved-views panel that reloads from the API, a
  colored SVG geometry overlay toggle on the crop, and a raw-IR JSON panel.
- Verified by hand end-to-end through a real browser (Playwright-driven):
  upload → lasso → save → select → extract → overlay → raw IR, with zero
  console errors.

## Dimension OCR — what it does and what was actually measured

`app/extract.py`'s `_extract_dimensions` OCRs the crop directly with
Tesseract at two scales (2x, 3x upscale + Otsu threshold), merges readings
within a ~20px bucket keeping the highest-confidence one, and links each
number to the nearest `object`-layer primitive as an **unconfirmed**
nearest-neighbor heuristic — never asserted as the correct association. It
reads **plain numbers and decimals only** into `Dimension.nominal`/`text_raw`.
`Dimension.tolerance` and `Dimension.gdt` are always `None` from this stage —
no tolerance or GD&T symbol parsing is attempted.

This *replaced* an earlier region-based approach (`app/ocr_dims.py`, still on
disk but no longer imported by `extract.py`) that preferred EasyOCR with a
Tesseract fallback. That approach was measured on the same real drawing
(`storage/uploads/012eeb226497.jpg`, 12 visible labels: 33, 28, 30, 65, 35,
91.5, 49.5, 21, 21, 13, 9, 33): region detection found 17 candidate regions
(vs. ~1 for naive whole-image thresholding), but OCR accuracy on those
regions was 0/12 — every visible dimension was missed, with low-confidence
single-digit misreads on small/JPEG-compressed text. That finding still
stands as a general signal that dimension OCR is hard on this class of
scanned/photographed drawing; it has not been re-measured against the current
inline-Tesseract implementation, which has no tesseract binary available in
this dev environment to test against (see below) — so 0 dimensions is the
only number actually observed for the current code path, not a comparative
result.

## What is stubbed or environment-limited

- **GD&T symbol** recognition (feature control frames, datums) is **not**
  implemented. The `Dimension.gdt` field exists in the schema but is never
  populated.
- **Tolerance parsing is not implemented** in the current OCR stage (see
  above) — the prior whole-image regex-based tolerance parser (`±X`, `+X/-Y`)
  was removed because the region-based OCR's character allowlist can't
  produce those symbols in the first place; keeping unreachable tolerance-
  parsing code would have been dead code asserting a capability that doesn't
  exist on this path.
- **Dimension→primitive association** (`Dimension.constrains`) is a
  nearest-centroid heuristic over OCR'd text boxes, restricted to `object`-
  layer primitives, surfaced as a link but **not asserted as correct** — it
  needs human confirmation, exactly as DESIGN.md specifies. The frontend
  labels this explicitly under the overlay.
- **Dimension OCR accuracy on real drawings is poor, measured, not hidden.**
  See the OCR section above; the prior region-based measurement found 0/12
  visible labels read correctly on the reference photo, and the current
  inline-Tesseract path has no tesseract binary to test against in this dev
  environment, so it returns 0 dimensions for an environment reason, not a
  verified-accurate one.
- **Line layer classification is a heuristic, not accurate, and its known
  failure mode was observed (not hidden) on a real crop.** Running extraction
  on `storage/crops/view_ec1ec440.png` (a tightly lassoed bottom-view crop of
  the real HJ-19 drawing, 254×132px) gave 18 primitives: 1 circle, 15 lines
  layer=`object`, 2 lines layer=`dimension`, 1 line layer=`unknown`. Visually
  overlaying these on the crop shows several of the 15 "object" lines are
  actually dimension witness/leader lines (the extension lines for the
  21/49.5/21/91.5 callouts and the leader crossings for 13/9/33) —
  misclassified as object. The root cause: the classifier's primary signal
  (line length > 10% of the view diagonal) is calibrated for full-sheet crops;
  on a small, tightly-cropped view the diagonal itself is small, so even short
  witness lines clear that bar and get classified as object. This is a real,
  observed limitation of the relative-length signal at this crop scale, not
  tuned away — a wider crop (or a signal that isn't relative to crop size)
  would need to replace or supplement it.
- The **multi-model router**, **view stitching/correspondence**, **3D
  reconciliation**, and the **CAD viewer** are designed in DESIGN.md but not
  built. `Correspondence` and `Feature3D` tables exist so the schema can
  express the full pipeline; they're populated only by `seed.py`'s synthetic
  example, never by a running stage.
- Projection convention defaults to **first-angle** (India / Europe);
  third-angle is supported via the `sheet_meta.projection` field but nothing
  currently sets it from real input (no parse-stage OCR of the title block).
