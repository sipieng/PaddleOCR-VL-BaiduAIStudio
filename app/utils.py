import hashlib
import os
import re
from pathlib import Path


_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_path_segment(segment: str) -> str:
    segment = segment.replace("\\", "/").split("/")[-1]
    segment = segment.strip().strip(".")
    segment = _SAFE_SEGMENT_RE.sub("_", segment)
    return segment or "file"


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guess_file_type(filename: str) -> int:
    # API uses: PDF=0, image=1
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return 0
    return 1


def split_relpath(relpath: str) -> list[str]:
    relpath = relpath.replace("\\", "/")
    relpath = relpath.lstrip("/")
    parts = [p for p in relpath.split("/") if p not in ("", ".", "..")]
    return parts
