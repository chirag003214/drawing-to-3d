"""
Pydantic request/response schemas for the API layer.

These are thin wrappers around the IR (app/models.py) for HTTP I/O. They do
not introduce any new concepts beyond what the IR already defines.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DrawingOut(BaseModel):
    id: str
    width: int
    height: int
    source_image_uri: Optional[str] = None


class ViewCreate(BaseModel):
    polygon: list[list[float]]  # [[x,y], ...] in CANVAS-display coordinates
    label: str  # front | top | side | section | detail | iso | info
    notes: Optional[str] = None
    px_per_mm: Optional[float] = None
    canvas_w: float
    canvas_h: float


class PrimitiveOut(BaseModel):
    id: str
    kind: str
    geom: dict
    layer: str
    confidence: float


class DimensionOut(BaseModel):
    id: str
    kind: str
    nominal: Optional[float] = None
    text_raw: Optional[str] = None
    tolerance: Optional[dict] = None
    constrains: list[str] = []
    gdt: Optional[dict] = None


class ViewOut(BaseModel):
    id: str
    drawing_id: str
    label: str
    crop_uri: Optional[str] = None
    mask_uri: Optional[str] = None
    notes: Optional[str] = None
    px_per_mm: Optional[float] = None
    crop_w: Optional[int] = None
    crop_h: Optional[int] = None


class ViewDetailOut(ViewOut):
    primitives: list[PrimitiveOut] = []
    dimensions: list[DimensionOut] = []


class ExtractResult(BaseModel):
    view_id: str
    primitives: list[PrimitiveOut]
    dimensions: list[DimensionOut]
    svg_overlay: str
