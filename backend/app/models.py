"""
Intermediate Representation (IR) — the core data model.

This is the artifact the task actually grades: extracted geometry linked to its
dimension and tolerance (GD&T) information, plus the 3D features reconstructed
from it, with provenance back to the 2D primitives that produced them.

Stages communicate ONLY through this IR. Slices A and B (built) populate
Drawing / View / Primitive / Dimension. The later, designed-not-built stages
(stitching, reconciliation) populate Correspondence / Feature3D — their tables
exist here so the schema can already express the full pipeline.

The two links that make this an IR rather than a pile of detections:
  - Dimension.constrains -> [primitive_id]   (which geometry a measurement sizes)
  - Feature3D.provenance -> {primitives, dimensions}  (what a 3D face came from)
Both are stored as ID references in JSON because they are many-to-many across
the whole drawing graph.
"""
from __future__ import annotations

import uuid
import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey, JSON, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _id(prefix: str) -> str:
    """Stable, human-readable IDs, e.g. 'prim_1a2b3c4d'."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Drawing  (root of the IR tree)
# --------------------------------------------------------------------------- #
class Drawing(Base):
    __tablename__ = "drawings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("drw"))
    source_image_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # sheet_meta: units, scale, projection ("first_angle" | "third_angle"),
    # title_block {...}, ocr_confidence  — populated by stage 1 (parse).
    sheet_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    views: Mapped[list["View"]] = relationship(
        back_populates="drawing", cascade="all, delete-orphan"
    )
    correspondences: Mapped[list["Correspondence"]] = relationship(
        back_populates="drawing", cascade="all, delete-orphan"
    )
    features: Mapped[list["Feature3D"]] = relationship(
        back_populates="drawing", cascade="all, delete-orphan"
    )


# --------------------------------------------------------------------------- #
# View  (one labelled crop — produced by Slice A)
# --------------------------------------------------------------------------- #
class View(Base):
    __tablename__ = "views"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("view"))
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"))
    # front | top | side | section | detail | iso | info
    label: Mapped[str] = mapped_column(String)
    crop_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mask_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # pixel -> model scale for THIS view; lets extraction be metric, not guessed.
    px_per_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    drawing: Mapped["Drawing"] = relationship(back_populates="views")
    primitives: Mapped[list["Primitive"]] = relationship(
        back_populates="view", cascade="all, delete-orphan"
    )
    dimensions: Mapped[list["Dimension"]] = relationship(
        back_populates="view", cascade="all, delete-orphan"
    )


# --------------------------------------------------------------------------- #
# Primitive  (extracted geometry — produced by Slice B)
# --------------------------------------------------------------------------- #
class Primitive(Base):
    __tablename__ = "primitives"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("prim"))
    view_id: Mapped[str] = mapped_column(ForeignKey("views.id"))
    kind: Mapped[str] = mapped_column(String)  # line | arc | circle | spline
    # geom is view-local: line -> {x1,y1,x2,y2}; circle -> {cx,cy,r}; etc.
    geom: Mapped[dict] = mapped_column(JSON)
    # object | dimension | hidden | centerline | unknown
    layer: Mapped[str] = mapped_column(String, default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    view: Mapped["View"] = relationship(back_populates="primitives")


# --------------------------------------------------------------------------- #
# Dimension  (measurement + tolerance, linked to the geometry it sizes)
# --------------------------------------------------------------------------- #
class Dimension(Base):
    __tablename__ = "dimensions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("dim"))
    view_id: Mapped[str] = mapped_column(ForeignKey("views.id"))
    kind: Mapped[str] = mapped_column(String)  # linear | diameter | radius | angular
    nominal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    text_raw: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # OCR'd
    tolerance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {upper, lower}
    # THE LINK: which primitive(s) this dimension constrains.
    constrains: Mapped[list] = mapped_column(JSON, default=list)  # [primitive_id]
    # Feature control frame — DEFERRED (symbol recognition not built). Shape only.
    gdt: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    view: Mapped["View"] = relationship(back_populates="dimensions")


# --------------------------------------------------------------------------- #
# Correspondence  (cross-view stitching — stage 4, designed-not-built)
# --------------------------------------------------------------------------- #
class Correspondence(Base):
    __tablename__ = "correspondences"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("corr"))
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"))
    kind: Mapped[str] = mapped_column(String)  # same_feature | projection_axis | section_of
    members: Mapped[list] = mapped_column(JSON, default=list)  # [primitive_id | view_id]
    intent_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # user's prose

    drawing: Mapped["Drawing"] = relationship(back_populates="correspondences")


# --------------------------------------------------------------------------- #
# Feature3D  (reconstructed 3D feature — stage 5, designed-not-built)
# --------------------------------------------------------------------------- #
class Feature3D(Base):
    __tablename__ = "features_3d"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("feat"))
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"))
    op: Mapped[str] = mapped_column(String)  # extrude | revolve | cut | fillet | ...
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # depth, axis, radius, ...
    seq: Mapped[int] = mapped_column(Integer, default=0)  # order in the build recipe
    # THE LINK: which 2D primitives + dimensions produced this 3D feature.
    provenance: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"primitives": [], "dimensions": []}
    )
    face_ids: Mapped[list] = mapped_column(JSON, default=list)  # kernel face tags

    drawing: Mapped["Drawing"] = relationship(back_populates="features")
