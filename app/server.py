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
    upload_dir = ensure_dir(task_dir / "_uploads")

    total_bytes = 0
    created_items = []
    for idx, f in enumerate(files):
        data = await f.read()
        size = len(data)
        total_bytes += size
        if size > settings.max_file_bytes:
            raise HTTPException(status_code=413, detail=f"单个文件过大：{f.filename}")
        if total_bytes > settings.max_total_bytes:
            raise HTTPException(status_code=413, detail="上传总大小超限")

        filename = safe_path_segment(f.filename or "file")
        rp = rel_list[idx] if idx < len(rel_list) else filename
        rp_parts = split_relpath(rp)
        rp_safe = (
            "/".join([safe_path_segment(p) for p in rp_parts]) if rp_parts else filename
        )

        tmp_path = upload_dir / f"{idx:05d}_{filename}"
        tmp_path.write_bytes(data)

        item = queue.enqueue_file(
            task_id=task.task_id,
            local_path=str(tmp_path),
            filename=filename,
            relpath=rp_safe,
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
        "message": task.message,
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
