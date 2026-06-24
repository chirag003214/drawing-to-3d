"""
FastAPI app wiring Slice A (upload/lasso/crop/label) and Slice B (CV extract)
to the IR. Every endpoint reads/writes app.models objects; no stage talks to
another stage except through the IR (see DESIGN.md principle 1).
"""
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image

from app.db import SessionLocal, init_db
from app.models import Drawing, View, Primitive, Dimension
from app.schemas import (
    DrawingOut, ViewCreate, ViewOut, ViewDetailOut, PrimitiveOut, DimensionOut,
    ExtractResult,
)
from app.storage import UPLOADS_DIR, CROPS_DIR, MASKS_DIR, to_uri, from_uri
from app.lasso import polygon_to_crop
from app.extract import extract as run_cv_extraction

init_db()

app = FastAPI(title="Drawing-to-3D IR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _view_out(v: View) -> ViewOut:
    crop_w = crop_h = None
    if v.crop_uri:
        try:
            with Image.open(from_uri(v.crop_uri)) as im:
                crop_w, crop_h = im.size
        except FileNotFoundError:
            pass
    return ViewOut(
        id=v.id, drawing_id=v.drawing_id, label=v.label, crop_uri=v.crop_uri,
        mask_uri=v.mask_uri, notes=v.notes, px_per_mm=v.px_per_mm,
        crop_w=crop_w, crop_h=crop_h,
    )


def _primitive_out(p: Primitive) -> PrimitiveOut:
    return PrimitiveOut(id=p.id, kind=p.kind, geom=p.geom, layer=p.layer, confidence=p.confidence)


def _dimension_out(d: Dimension) -> DimensionOut:
    return DimensionOut(
        id=d.id, kind=d.kind, nominal=d.nominal, text_raw=d.text_raw,
        tolerance=d.tolerance, constrains=d.constrains, gdt=d.gdt,
    )


_LAYER_COLORS = {
    "object": "#1f6feb",
    "dimension": "#d29922",
    "centerline": "#8957e5",
    "hidden": "#6e7681",
    "unknown": "#bbbbbb",
}


def _build_svg(width: int, height: int, primitives: list[dict]) -> str:
    """app.extract.extract() returns geometry only, no overlay -- the frontend
    renders its own SVG client-side from ViewDetailOut.primitives, so this is
    only here to keep the ExtractResult response schema (svg_overlay: str)
    satisfied; nothing currently consumes the string itself."""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    for p in primitives:
        color = _LAYER_COLORS.get(p["layer"], "#bbbbbb")
        opacity = 0.4 if p["confidence"] < 0.5 else 0.9
        g = p["geom"]
        if p["kind"] == "line":
            parts.append(
                f'<line x1="{g["x1"]}" y1="{g["y1"]}" x2="{g["x2"]}" y2="{g["y2"]}" '
                f'stroke="{color}" stroke-width="2" opacity="{opacity}"/>'
            )
        elif p["kind"] in ("circle", "arc"):
            parts.append(
                f'<circle cx="{g["cx"]}" cy="{g["cy"]}" r="{g["r"]}" '
                f'fill="none" stroke="{color}" stroke-width="2" opacity="{opacity}"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


@app.post("/drawings", response_model=DrawingOut)
def create_drawing(file: UploadFile = File(...)):
    raw = file.file.read()
    ext = (file.filename or "upload").split(".")[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "bmp", "tif", "tiff"):
        ext = "png"
    fname = f"{uuid.uuid4().hex[:12]}.{ext}"
    dest = UPLOADS_DIR / fname
    dest.write_bytes(raw)

    try:
        with Image.open(dest) as im:
            width, height = im.size
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read image: {e}")

    with SessionLocal() as s:
        drawing = Drawing(
            source_image_uri=to_uri(dest),
            sheet_meta={"units": "mm", "width_px": width, "height_px": height},
        )
        s.add(drawing)
        s.commit()
        return DrawingOut(id=drawing.id, width=width, height=height, source_image_uri=drawing.source_image_uri)


@app.get("/drawings/{drawing_id}", response_model=DrawingOut)
def get_drawing(drawing_id: str):
    with SessionLocal() as s:
        d = s.get(Drawing, drawing_id)
        if d is None:
            raise HTTPException(404, "drawing not found")
        meta = d.sheet_meta or {}
        return DrawingOut(
            id=d.id, width=meta.get("width_px", 0), height=meta.get("height_px", 0),
            source_image_uri=d.source_image_uri,
        )


@app.post("/drawings/{drawing_id}/views", response_model=ViewOut)
def create_view(drawing_id: str, body: ViewCreate):
    with SessionLocal() as s:
        drawing = s.get(Drawing, drawing_id)
        if drawing is None:
            raise HTTPException(404, "drawing not found")
        if not drawing.source_image_uri:
            raise HTTPException(400, "drawing has no source image")

        src_path = from_uri(drawing.source_image_uri)
        with Image.open(src_path) as image:
            try:
                crop_rgba, mask, bbox = polygon_to_crop(
                    image, body.polygon, body.canvas_w, body.canvas_h
                )
            except ValueError as e:
                raise HTTPException(400, str(e))

        view = View(
            drawing_id=drawing.id,
            label=body.label,
            notes=body.notes,
            px_per_mm=body.px_per_mm,
        )
        s.add(view)
        s.flush()  # assign view.id

        crop_path = CROPS_DIR / f"{view.id}.png"
        mask_path = MASKS_DIR / f"{view.id}_mask.png"
        crop_rgba.save(crop_path)
        Image.fromarray(mask).save(mask_path)

        view.crop_uri = to_uri(crop_path)
        view.mask_uri = to_uri(mask_path)
        s.commit()
        return _view_out(view)


@app.get("/drawings/{drawing_id}/views", response_model=list[ViewOut])
def list_views(drawing_id: str):
    with SessionLocal() as s:
        drawing = s.get(Drawing, drawing_id)
        if drawing is None:
            raise HTTPException(404, "drawing not found")
        return [_view_out(v) for v in drawing.views]


@app.get("/views/{view_id}", response_model=ViewDetailOut)
def get_view(view_id: str):
    with SessionLocal() as s:
        v = s.get(View, view_id)
        if v is None:
            raise HTTPException(404, "view not found")
        base = _view_out(v)
        return ViewDetailOut(
            **base.model_dump(),
            primitives=[_primitive_out(p) for p in v.primitives],
            dimensions=[_dimension_out(d) for d in v.dimensions],
        )


@app.get("/views/{view_id}/crop")
def get_view_crop(view_id: str):
    with SessionLocal() as s:
        v = s.get(View, view_id)
        if v is None or not v.crop_uri:
            raise HTTPException(404, "crop not found")
        path = from_uri(v.crop_uri)
        if not path.exists():
            raise HTTPException(404, "crop file missing on disk")
        return FileResponse(path, media_type="image/png")


@app.post("/views/{view_id}/extract", response_model=ExtractResult)
def extract(view_id: str):
    with SessionLocal() as s:
        v = s.get(View, view_id)
        if v is None or not v.crop_uri:
            raise HTTPException(404, "view or crop not found")
        crop_path = from_uri(v.crop_uri)
        if not crop_path.exists():
            raise HTTPException(404, "crop file missing on disk")

        # Re-running extract should replace prior results, not accumulate them.
        for p in list(v.primitives):
            s.delete(p)
        for d in list(v.dimensions):
            s.delete(d)
        s.flush()

        result = run_cv_extraction(str(crop_path))
        primitives, dimensions = result["primitives"], result["dimensions"]

        # extract.py tags each primitive with its own temp id (used by
        # _extract_dimensions' nearest-object heuristic in `constrains`); map
        # those temp ids to the real, DB-assigned Primitive ids once persisted.
        prim_objs = []
        temp_id_to_obj = {}
        for p in primitives:
            obj = Primitive(view_id=v.id, kind=p["kind"], geom=p["geom"], layer=p["layer"], confidence=p["confidence"])
            s.add(obj)
            prim_objs.append(obj)
            temp_id_to_obj[p["id"]] = obj
        s.flush()  # assign real Primitive ids before resolving dimension links

        dim_objs = []
        for d in dimensions:
            real_ids = [temp_id_to_obj[tid].id for tid in d.get("constrains", []) if tid in temp_id_to_obj]
            obj = Dimension(
                view_id=v.id, kind=d["kind"], nominal=d.get("nominal"),
                text_raw=d.get("text_raw"), tolerance=d.get("tolerance"),
                constrains=real_ids, gdt=d.get("gdt"),
            )
            s.add(obj)
            dim_objs.append(obj)
        s.commit()

        with Image.open(crop_path) as im:
            svg_w, svg_h = im.size
        svg = _build_svg(svg_w, svg_h, primitives)

        return ExtractResult(
            view_id=v.id,
            primitives=[_primitive_out(p) for p in prim_objs],
            dimensions=[_dimension_out(d) for d in dim_objs],
            svg_overlay=svg,
        )
