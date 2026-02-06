import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .utils import ensure_dir, safe_path_segment


@dataclass(frozen=True)
class MaterializedItem:
    md_files: list[str]
    assets: list[str]


def materialize_result_to_dir(
    result: dict[str, Any], output_dir: Path
) -> MaterializedItem:
    ensure_dir(output_dir)
    md_files: list[str] = []
    assets: list[str] = []

    layout_results = result.get("layoutParsingResults") or []
    for i, res in enumerate(layout_results):
        md_path = output_dir / f"doc_{i}.md"
        md_text = ((res.get("markdown") or {}).get("text")) or ""
        md_path.write_text(md_text, encoding="utf-8")
        md_files.append(str(md_path))

        images = ((res.get("markdown") or {}).get("images")) or {}
        for img_path, img_url in images.items():
            img_rel = Path(
                *[
                    safe_path_segment(p)
                    for p in str(img_path).replace("\\", "/").split("/")
                    if p
                ]
            )
            full_img_path = output_dir / img_rel
            ensure_dir(full_img_path.parent)
            img_bytes = requests.get(img_url, timeout=60).content
            full_img_path.write_bytes(img_bytes)
            assets.append(str(full_img_path))

        output_images = res.get("outputImages") or {}
        for img_name, img_url in output_images.items():
            name = safe_path_segment(str(img_name))
            filename = output_dir / f"{name}_{i}.jpg"
            img_resp = requests.get(img_url, timeout=60)
            if img_resp.status_code == 200:
                filename.write_bytes(img_resp.content)
                assets.append(str(filename))

    return MaterializedItem(md_files=md_files, assets=assets)
