"""
Seed + contract test for the IR.

Proves the data model works END TO END before any UI or CV exists:

  1. Inserts a small but COMPLETE IR tree:
        Drawing -> View -> (2 Primitives, 1 Dimension)
                -> 2 Feature3D (the designed-not-built stage), with provenance
  2. Reopens the database in a FRESH session (so nothing is cached) and:
        - asserts the Dimension.constrains link resolves to a real Primitive
        - asserts each Feature3D.provenance resolves to real Primitives + Dimensions
  3. Prints the IR as a readable tree.

If this runs clean, the IR can express the one thing the task grades:
geometry linked to its tolerance, linked forward to the 3D feature it drives.

Run from the backend/ directory:
    python seed.py
"""
from app.db import SessionLocal, init_db
from app.models import Drawing, View, Primitive, Dimension, Feature3D


def build_example() -> str:
    """Insert one fully-linked drawing. Returns its id."""
    with SessionLocal() as s:
        # --- Drawing + sheet metadata (stage 1 output) -----------------------
        drawing = Drawing(
            source_image_uri="storage/uploads/bracket.png",
            sheet_meta={
                "units": "mm",
                "scale": "1:2",
                "projection": "first_angle",  # India / Europe convention
                "title_block": {"part_no": "BRK-001", "material": "Al 6061"},
                "ocr_confidence": 0.0,  # parse stage not built yet
            },
        )

        # --- View (Slice A output) -------------------------------------------
        front = View(
            label="front",
            crop_uri="storage/crops/bracket_front.png",
            mask_uri="storage/masks/bracket_front_mask.png",
            notes="Front view, lassoed manually.",
            px_per_mm=4.0,
        )
        drawing.views.append(front)

        # --- Primitives (Slice B output) -------------------------------------
        outline = Primitive(
            kind="line",
            geom={"x1": 0, "y1": 0, "x2": 200, "y2": 0},
            layer="object",
            confidence=0.97,
        )
        hole = Primitive(
            kind="circle",
            geom={"cx": 100, "cy": 50, "r": 20},
            layer="object",
            confidence=0.93,
        )
        front.primitives.extend([outline, hole])

        # Flush so default IDs are assigned before we reference them below.
        s.add(drawing)
        s.flush()

        # --- Dimension linked to the hole (the geometry<->tolerance link) ----
        dia = Dimension(
            kind="diameter",
            nominal=10.0,
            text_raw="\u00d810 \u00b10.05",  # "Ø10 ±0.05"
            tolerance={"upper": 0.05, "lower": -0.05},
            constrains=[hole.id],  # <-- THE LINK
        )
        front.dimensions.append(dia)
        s.flush()  # assign dia.id before it is referenced in provenance

        # --- 3D features (stage 5; designed, shown here only to prove the
        #     schema can carry provenance back to 2D) -------------------------
        extrude = Feature3D(
            op="extrude",
            params={"profile": outline.id, "depth_mm": 50},
            seq=0,
            provenance={"primitives": [outline.id], "dimensions": []},
        )
        cut = Feature3D(
            op="cut",
            params={"profile": hole.id, "through": True},
            seq=1,
            provenance={"primitives": [hole.id], "dimensions": [dia.id]},  # <-- carries tolerance
        )
        drawing.features.extend([extrude, cut])

        s.commit()
        return drawing.id


def verify(drawing_id: str) -> None:
    """Reopen in a fresh session and assert every cross-link resolves."""
    with SessionLocal() as s:
        d = s.get(Drawing, drawing_id)
        assert d is not None, "drawing not found after commit"

        # Build id -> object lookups across the whole drawing.
        prims = {p.id: p for v in d.views for p in v.primitives}
        dims = {dm.id: dm for v in d.views for dm in v.dimensions}

        # (1) Dimension.constrains must point at a real primitive.
        for v in d.views:
            for dm in v.dimensions:
                for pid in dm.constrains:
                    assert pid in prims, f"dimension {dm.id} constrains missing primitive {pid}"
        print("PASS  every Dimension.constrains resolves to a real Primitive")

        # (2) Feature3D.provenance must resolve to real primitives + dimensions.
        for f in d.features:
            for pid in f.provenance.get("primitives", []):
                assert pid in prims, f"feature {f.id} provenance missing primitive {pid}"
            for did in f.provenance.get("dimensions", []):
                assert did in dims, f"feature {f.id} provenance missing dimension {did}"
        print("PASS  every Feature3D.provenance resolves to real Primitives + Dimensions")

        # (3) The graded round-trip: from a 3D feature, recover the tolerance.
        cut = next(f for f in d.features if f.op == "cut")
        gov_dim = dims[cut.provenance["dimensions"][0]]
        assert gov_dim.tolerance == {"upper": 0.05, "lower": -0.05}
        print(
            f"PASS  3D feature '{cut.op}' traces back to tolerance "
            f"{gov_dim.tolerance} via {gov_dim.text_raw}"
        )

        _print_tree(d, prims, dims)


def _print_tree(d, prims, dims) -> None:
    print("\nIR TREE")
    print(f"Drawing {d.id}  [{d.sheet_meta['units']}, {d.sheet_meta['projection']}]")
    for v in d.views:
        print(f"  View {v.id}  label={v.label}  px_per_mm={v.px_per_mm}")
        for p in v.primitives:
            print(f"    Primitive {p.id}  {p.kind:<6} layer={p.layer} conf={p.confidence}")
        for dm in v.dimensions:
            tgt = ", ".join(dm.constrains)
            print(f"    Dimension {dm.id}  {dm.text_raw}  -> constrains [{tgt}]")
    for f in sorted(d.features, key=lambda x: x.seq):
        prov = f.provenance
        print(
            f"  Feature3D {f.id}  op={f.op:<7} seq={f.seq}  "
            f"provenance: prims={prov['primitives']} dims={prov['dimensions']}"
        )


if __name__ == "__main__":
    init_db(reset=True)
    did = build_example()
    print(f"seeded drawing {did}\n")
    verify(did)
    print("\nALL CONTRACT CHECKS PASSED")
