"""
Filesystem media store. The IR (models.py) stores only URIs into this tree;
raw bytes never live in the database (see DESIGN.md "IR vs media store").
"""
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"
UPLOADS_DIR = STORAGE_ROOT / "uploads"
CROPS_DIR = STORAGE_ROOT / "crops"
MASKS_DIR = STORAGE_ROOT / "masks"

for d in (UPLOADS_DIR, CROPS_DIR, MASKS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def to_uri(path: Path) -> str:
    """Store paths relative to the repo root, POSIX-style, matching seed.py's convention."""
    repo_root = STORAGE_ROOT.parent
    return path.resolve().relative_to(repo_root).as_posix()


def from_uri(uri: str) -> Path:
    repo_root = STORAGE_ROOT.parent
    return (repo_root / uri).resolve()
