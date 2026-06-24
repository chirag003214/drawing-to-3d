"""
Database wiring for the IR.

Prototype storage is SQLite (zero-config: a single file, no server). The models
use plain columns + JSON, so moving to Postgres + JSONB later is mechanical:
swap the engine URL and the JSON columns map straight onto JSONB.

Image BYTES never live here — only their paths (crop_uri / mask_uri /
source_image_uri). Raw pixels live on disk under /storage. This is the
"IR vs. media store" split from the design document.
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

DB_PATH = Path(__file__).resolve().parent.parent / "ir.db"
ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)


def init_db(reset: bool = False) -> None:
    """Create all IR tables. If reset=True, drop the existing DB file first."""
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    Base.metadata.create_all(ENGINE)
