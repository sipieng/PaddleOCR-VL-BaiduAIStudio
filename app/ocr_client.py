import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


@dataclass(frozen=True)
class OcrOptions:
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_chart_recognition: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "useDocOrientationClassify": self.use_doc_orientation_classify,
            "useDocUnwarping": self.use_doc_unwarping,
            "useChartRecognition": self.use_chart_recognition,
        }


class BaiduPaddleOcrClient:
    def __init__(
        self,
        *,
        token: str,
        api_url: str = "",
        job_url: str = "",
        timeout_s: float = 60.0,
    ) -> None:
        self._token = token
        self._api_url = api_url
        self._job_url = job_url
        self._timeout_s = timeout_s

    def submit_sync_base64(
        self, *, file_bytes: bytes, file_type: int, options: OcrOptions
    ) -> dict[str, Any]:
        if not self._api_url:
            raise RuntimeError("Missing BAIDU_PADDLE_OCR_API_URL for sync mode")
        file_data = base64.b64encode(file_bytes).decode("ascii")
        headers = {
            "Authorization": f"token {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "file": file_data,
            "fileType": int(file_type),
            **options.to_payload(),
        }
        resp = requests.post(
            self._api_url, json=payload, headers=headers, timeout=self._timeout_s
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Sync OCR failed: HTTP {resp.status_code}: {resp.text[:1000]}"
            )
        data = resp.json()
        return data["result"]

    def submit_job(
        self, *, file_path: str, options: OcrOptions, model: str = "PaddleOCR-VL-1.5"
    ) -> str:
        if not self._job_url:
            raise RuntimeError("Missing BAIDU_PADDLE_OCR_JOB_URL for async mode")
        headers = {"Authorization": f"bearer {self._token}"}
        data = {
            "model": model,
            "optionalPayload": json.dumps(options.to_payload(), ensure_ascii=False),
        }
        with open(file_path, "rb") as f:
            files = {"file": f}
            resp = requests.post(
                self._job_url,
                headers=headers,
                data=data,
                files=files,
                timeout=self._timeout_s,
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Job submit failed: HTTP {resp.status_code}: {resp.text[:1000]}"
            )
        return resp.json()["data"]["jobId"]

    def poll_job(
        self,
        *,
        job_id: str,
        poll_interval_s: float = 3.0,
        max_wait_s: float = 15 * 60.0,
    ) -> dict[str, Any]:
        if not self._job_url:
            raise RuntimeError("Missing BAIDU_PADDLE_OCR_JOB_URL for async mode")
        headers = {"Authorization": f"bearer {self._token}"}
        deadline = time.time() + max_wait_s
        last = None
        while time.time() < deadline:
            resp = requests.get(
                f"{self._job_url}/{job_id}", headers=headers, timeout=self._timeout_s
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Job poll failed: HTTP {resp.status_code}: {resp.text[:1000]}"
                )
            last = resp.json()["data"]
            state = last.get("state")
            if state == "done":
                return last
            if state == "failed":
                raise RuntimeError(
                    f"Job failed: {last.get('errorMsg', 'unknown error')}"
                )
            time.sleep(poll_interval_s)
        raise RuntimeError(f"Job timeout after {max_wait_s}s; last={last}")

    def download_jsonl(self, *, jsonl_url: str) -> str:
        resp = requests.get(jsonl_url, timeout=self._timeout_s)
        resp.raise_for_status()
        return resp.text


def parse_jsonl_results(jsonl_text: str) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        pages.append(obj["result"])
    return pages
