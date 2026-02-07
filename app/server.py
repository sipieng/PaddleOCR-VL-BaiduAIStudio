from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .ocr_client import BaiduPaddleOcrClient, OcrOptions
from .task_queue import TaskQueue
from .utils import ensure_dir, safe_path_segment, split_relpath


app = FastAPI(title="PaddleOCR-VL Local Web UI")


def _options_from_form(
    use_doc_orientation_classify: bool,
    use_doc_unwarping: bool,
    use_chart_recognition: bool,
) -> OcrOptions:
    return OcrOptions(
        use_doc_orientation_classify=use_doc_orientation_classify,
        use_doc_unwarping=use_doc_unwarping,
        use_chart_recognition=use_chart_recognition,
    )


client = BaiduPaddleOcrClient(
    token=settings.baidu_token,
    api_url=settings.baidu_api_url,
    job_url=settings.baidu_job_url,
)
queue = TaskQueue(
    client=client,
    output_root=settings.output_root,
    concurrency=settings.default_concurrency,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    index_file = STATIC_DIR / "index.html"
    return index_file.read_text(encoding="utf-8")


@app.post("/api/tasks")
async def create_task(
    files: list[UploadFile] = File(...),
    relpaths: Optional[str] = Form(None),
    force_async: bool = Form(False),
    use_doc_orientation_classify: bool = Form(False),
    use_doc_unwarping: bool = Form(False),
    use_chart_recognition: bool = Form(False),
) -> dict[str, Any]:
    try:
        settings.validate()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))

    # relpaths is a JSON array of strings matching `files` order.
    rel_list: list[str] = []
    if relpaths:
        import json

        try:
            rel_list = json.loads(relpaths)
        except Exception:
            raise HTTPException(status_code=400, detail="relpaths 必须是 JSON 数组")
    if rel_list and len(rel_list) != len(files):
        raise HTTPException(status_code=400, detail="relpaths 数量必须与 files 一致")

    opt = _options_from_form(
        use_doc_orientation_classify, use_doc_unwarping, use_chart_recognition
    )
    task = queue.create_task()
    task_dir = ensure_dir(Path(settings.output_root) / task.task_id)
    inputs_dir = ensure_dir(task_dir / "inputs")

    total_bytes = 0
    created_items = []
    for idx, f in enumerate(files):
        # Server-side format validation (frontend also filters).
        name_raw = f.filename or "file"
        name_lower = name_raw.lower()
        ct = (f.content_type or "").lower()
        is_pdf = ct == "application/pdf" or name_lower.endswith(".pdf")
        is_img = ct.startswith("image/") or name_lower.endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
        )
        if not (is_pdf or is_img):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式：{name_raw}（仅支持图片与 PDF）",
            )

        data = await f.read()
        size = len(data)
        total_bytes += size
        if size > settings.max_file_bytes:
            raise HTTPException(status_code=413, detail=f"单个文件过大：{f.filename}")
        if total_bytes > settings.max_total_bytes:
            raise HTTPException(status_code=413, detail="上传总大小超限")

        original_name = f.filename or "file"
        filename = safe_path_segment(original_name)

        rp = rel_list[idx] if idx < len(rel_list) else original_name
        display_parts = split_relpath(rp)
        display_relpath = "/".join(display_parts) if display_parts else original_name

        # Write uploaded file directly into task inputs/{relpath} (sanitized for filesystem).
        rel_safe_parts = [safe_path_segment(p) for p in display_parts]
        if not rel_safe_parts:
            rel_safe_parts = [filename]
        dest_path = inputs_dir.joinpath(*rel_safe_parts)
        ensure_dir(dest_path.parent)
        if dest_path.exists():
            stem = dest_path.stem
            suffix = dest_path.suffix
            k = 1
            while True:
                cand = dest_path.with_name(f"{stem}_{k}{suffix}")
                if not cand.exists():
                    dest_path = cand
                    # Keep UI display name aligned with the stored file.
                    last = display_parts[-1] if display_parts else original_name
                    if "." in last:
                        base, ext = last.rsplit(".", 1)
                        last2 = f"{base}_{k}.{ext}"
                    else:
                        last2 = f"{last}_{k}"
                    if display_parts:
                        display_parts[-1] = last2
                        display_relpath = "/".join(display_parts)
                    else:
                        display_relpath = last2
                    break
                k += 1
        dest_path.write_bytes(data)

        item = queue.enqueue_file(
            task_id=task.task_id,
            local_path=str(dest_path),
            filename=filename,
            relpath=display_relpath,
            size=size,
            force_async=force_async,
            options=opt,
        )
        created_items.append(
            {
                "itemId": item.item_id,
                "filename": item.filename,
                "relpath": item.relpath,
                "status": item.status,
            }
        )

    return {"taskId": task.task_id, "items": created_items}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "taskId": task.task_id,
        "status": task.status,
        "total": task.total,
        "done": task.done,
        "failed": task.failed,
        "canceled": getattr(task, "canceled", 0),
        "message": task.message,
    }


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    queue.cancel_task(task_id)
    task2 = queue.get_task(task_id)
    return {
        "taskId": task_id,
        "status": task2.status if task2 else "canceled",
        "message": task2.message if task2 else "已停止",
    }


@app.get("/api/tasks/{task_id}/items")
def list_items(task_id: str) -> dict[str, Any]:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "taskId": task.task_id,
        "items": [
            {
                "itemId": it.item_id,
                "filename": it.filename,
                "relpath": it.relpath,
                "size": it.size,
                "status": it.status,
                "error": it.error,
                "mdFiles": it.md_files,
                "assets": it.assets,
            }
            for it in task.items
        ],
    }


@app.get("/api/tasks/{task_id}/items/{item_id}/md")
def get_item_md(task_id: str, item_id: str) -> dict[str, Any]:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    item = next((x for x in task.items if x.item_id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not item.md_files:
        raise HTTPException(status_code=404, detail="该文件暂无 Markdown 输出")

    md_path = Path(item.md_files[0])
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Markdown 文件不存在")
    return {"itemId": item.item_id, "md": md_path.read_text(encoding="utf-8")}


@app.get("/api/tasks/{task_id}/download.zip")
def download_zip(task_id: str) -> FileResponse:
    task_dir = Path(settings.output_root) / task_id
    if not task_dir.exists():
        raise HTTPException(status_code=404, detail="任务目录不存在")

    import zipfile
    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{task_id}.zip")
    tmp.close()
    zip_path = Path(tmp.name)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in task_dir.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(task_dir)
            zf.write(p, arcname=str(rel))

    return FileResponse(
        path=str(zip_path),
        filename=f"{task_id}.zip",
        media_type="application/zip",
    )
