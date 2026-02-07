import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .ocr_client import BaiduPaddleOcrClient, OcrOptions, parse_jsonl_results
from .storage import materialize_result_to_dir
from .utils import ensure_dir, guess_file_type, safe_path_segment


@dataclass
class TaskItem:
    item_id: str
    filename: str
    relpath: str
    size: int
    status: str = "queued"  # queued|running|done|failed|canceled
    error: str = ""
    output_dir: str = ""
    md_files: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)


@dataclass
class Task:
    task_id: str
    created_at: float
    status: str = "queued"  # queued|running|done|failed|canceled
    total: int = 0
    done: int = 0
    failed: int = 0
    canceled: int = 0
    message: str = ""
    items: list[TaskItem] = field(default_factory=list)


@dataclass(frozen=True)
class EnqueuedItem:
    task_id: str
    item_id: str
    local_path: str
    filename: str
    relpath: str
    force_async: bool
    options: OcrOptions


class TaskQueue:
    def __init__(
        self, *, client: BaiduPaddleOcrClient, output_root: str, concurrency: int = 2
    ) -> None:
        self._client = client
        self._output_root = Path(output_root)
        ensure_dir(self._output_root)
        self._q: queue.Queue[EnqueuedItem] = queue.Queue()
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()

        for idx in range(max(1, int(concurrency))):
            t = threading.Thread(target=self._worker, name=f"worker-{idx}", daemon=True)
            t.start()
            self._workers.append(t)

    def create_task(self) -> Task:
        task_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        task = Task(task_id=task_id, created_at=time.time())
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.status in ("done", "failed", "canceled"):
                return
            task.status = "canceled"
            task.message = "已停止识别"
            for it in task.items:
                if it.status == "queued":
                    it.status = "canceled"
                    task.canceled += 1

    def enqueue_file(
        self,
        *,
        task_id: str,
        local_path: str,
        filename: str,
        relpath: str,
        size: int,
        force_async: bool,
        options: OcrOptions,
    ) -> TaskItem:
        item_id = uuid.uuid4().hex[:10]
        item = TaskItem(
            item_id=item_id,
            filename=filename,
            relpath=relpath,
            size=size,
            output_dir=str(self._output_root / task_id),
        )
        with self._lock:
            task = self._tasks[task_id]
            task.items.append(item)
            task.total += 1
            task.status = "queued" if task.done + task.failed == 0 else task.status
        self._q.put(
            EnqueuedItem(
                task_id=task_id,
                item_id=item_id,
                local_path=local_path,
                filename=filename,
                relpath=relpath,
                force_async=force_async,
                options=options,
            )
        )
        return item

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            task = self.get_task(job.task_id)
            if not task or task.status == "canceled":
                self._q.task_done()
                continue

            with self._lock:
                task.status = "running"
                item = next((x for x in task.items if x.item_id == job.item_id), None)
                if item:
                    item.status = "running"

            try:
                md_files, assets = self._process_one(job)
                with self._lock:
                    task.done += 1
                    if item:
                        item.status = "done"
                        item.md_files = md_files
                        item.assets = assets
            except TaskCanceled:
                with self._lock:
                    # cancel_task() counts queued->canceled; running item gets counted here.
                    if item and item.status != "canceled":
                        item.status = "canceled"
                        task.canceled += 1
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    task.failed += 1
                    if item:
                        item.status = "failed"
                        item.error = str(e)
            finally:
                with self._lock:
                    if (
                        task.done + task.failed + task.canceled >= task.total
                        and task.status != "canceled"
                    ):
                        task.status = "done" if task.failed == 0 else "failed"
                self._q.task_done()

    def _process_one(self, job: EnqueuedItem) -> tuple[list[str], list[str]]:
        task = self.get_task(job.task_id)
        if not task or task.status == "canceled":
            raise TaskCanceled()

        task_dir = ensure_dir(self._output_root / job.task_id)
        # Input file is already written to output/{task_id}/inputs/... by server.
        src = Path(job.local_path)
        if not src.exists():
            raise RuntimeError(f"Input file missing: {src}")

        dest_path = src

        file_type = guess_file_type(job.filename)
        use_async = job.force_async or file_type == 0
        md_files: list[str] = []
        assets: list[str] = []
        if use_async:
            job_id = self._client.submit_job(
                file_path=str(dest_path), options=job.options
            )
            try:
                job_data = self._client.poll_job(
                    job_id=job_id,
                    should_cancel=lambda: (
                        self.get_task(job.task_id) or Task("", 0)
                    ).status
                    == "canceled",
                )
            except RuntimeError as e:
                if str(e) == "canceled":
                    raise TaskCanceled() from e
                raise
            if (self.get_task(job.task_id) or Task("", 0)).status == "canceled":
                raise TaskCanceled()
            json_url = (job_data.get("resultUrl") or {}).get("jsonUrl")
            if not json_url:
                raise RuntimeError("Job completed but missing resultUrl.jsonUrl")
            raw_dir = ensure_dir(task_dir / "raw")
            jsonl_text = self._client.download_jsonl(jsonl_url=json_url)
            (raw_dir / f"{safe_path_segment(job.item_id)}.jsonl").write_text(
                jsonl_text, encoding="utf-8"
            )
            pages = parse_jsonl_results(jsonl_text)
            # Merge pages into a single materialization dir; keep page order.
            for page_idx, page_result in enumerate(pages):
                if (self.get_task(job.task_id) or Task("", 0)).status == "canceled":
                    raise TaskCanceled()
                out_dir = ensure_dir(
                    task_dir / safe_path_segment(job.item_id) / f"page_{page_idx}"
                )
                m = materialize_result_to_dir(page_result, out_dir)
                md_files.extend(m.md_files)
                assets.extend(m.assets)

            merged_md = self._write_merged_markdown(
                task_dir / safe_path_segment(job.item_id), md_files
            )
            if merged_md:
                md_files = [merged_md, *md_files]
        else:
            if (self.get_task(job.task_id) or Task("", 0)).status == "canceled":
                raise TaskCanceled()
            file_bytes = dest_path.read_bytes()
            result = self._client.submit_sync_base64(
                file_bytes=file_bytes, file_type=file_type, options=job.options
            )
            out_dir = ensure_dir(task_dir / safe_path_segment(job.item_id))
            m = materialize_result_to_dir(result, out_dir)
            md_files.extend(m.md_files)
            assets.extend(m.assets)

        return md_files, assets

    def _write_merged_markdown(self, item_dir: Path, md_files: list[str]) -> str:
        # For multi-page PDFs, we materialize per-page md under item_dir/page_*/doc_*.md.
        # Create a merged markdown for convenience.
        if len(md_files) <= 1:
            return ""
        parts: list[str] = []
        for p in md_files:
            try:
                text = Path(p).read_text(encoding="utf-8")
            except Exception:
                text = ""
            text = text.strip("\n")
            parts.append(text)
        merged_text = "\n\n---\n\n".join([x for x in parts if x])
        if not merged_text.strip():
            return ""
        out = ensure_dir(item_dir) / "merged.md"
        out.write_text(merged_text + "\n", encoding="utf-8")
        return str(out)


class TaskCanceled(Exception):
    pass
