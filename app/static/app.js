let selected = [];
let taskId = null;
let pollTimer = null;
let activeItemId = null;
let lastTaskStatus = null;
let lastTaskTotal = 0;
let lastTaskDone = 0;
let lastTaskFailed = 0;
let lastTaskCanceled = 0;

const el = (id) => document.getElementById(id);

function fmtBytes(n) {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let x = n;
  while (x >= 1024 && i < units.length - 1) {
    x /= 1024;
    i += 1;
  }
  return `${x.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function renderQueue(items) {
  const list = el("queueList");
  list.classList.remove("empty");
  list.innerHTML = "";
  for (const it of items) {
    const row = document.createElement("div");
    row.className = "row";
    if (it.itemId && it.itemId === activeItemId) row.classList.add("active");
    const left = document.createElement("div");
    left.className = "rowLeft";
    const badge = document.createElement("div");
    badge.className = "badge";
    if (it.status === "done") badge.classList.add("ok");
    else if (it.status === "running") badge.classList.add("run");
    else if (it.status === "failed") badge.classList.add("fail");
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = it.relpath || it.filename;
    name.title = it.relpath || it.filename || "";

    left.appendChild(badge);
    left.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "meta";
    if (it.status === "failed") meta.textContent = it.error ? `失败：${it.error}` : "失败";
    else if (it.status === "done") meta.textContent = "完成";
    else if (it.status === "running") meta.textContent = "识别中…";
    else meta.textContent = it.size ? fmtBytes(it.size) : "等待中";

    if (it.itemId) {
      row.style.cursor = "pointer";
      row.addEventListener("click", () => selectItem(it));
    }
    row.appendChild(left);
    row.appendChild(meta);
    list.appendChild(row);
  }
}

function setStatus(text) {
  el("taskStatus").textContent = text;
}

function isSupportedFile(file) {
  const name = (file && file.name ? file.name : "").toLowerCase();
  const type = file && file.type ? file.type : "";
  if (type === "application/pdf" || name.endsWith(".pdf")) return true;
  if (type.startsWith("image/")) return true;
  return (
    name.endsWith(".png") ||
    name.endsWith(".jpg") ||
    name.endsWith(".jpeg") ||
    name.endsWith(".webp") ||
    name.endsWith(".bmp") ||
    name.endsWith(".tif") ||
    name.endsWith(".tiff")
  );
}

async function refreshTask() {
  if (!taskId) return;
  const t = await fetch(`/api/tasks/${taskId}`).then((r) => r.json());
  lastTaskStatus = t.status;
  lastTaskTotal = t.total || 0;
  lastTaskDone = t.done || 0;
  lastTaskFailed = t.failed || 0;
  lastTaskCanceled = t.canceled || 0;

  const extra = lastTaskCanceled ? `  已停止：${lastTaskCanceled}` : "";
  setStatus(`任务状态：${t.status}  进度：${t.done}/${t.total}  失败：${t.failed}${extra}`);
  el("btnDownload").disabled = !(t.status === "done" || t.status === "failed" || t.status === "canceled");
  el("btnStop").disabled = !(t.status === "running" || t.status === "queued");
  // After a task finishes, allow clearing the UI even if no local selection exists.
  if (t.status === "done" || t.status === "failed" || t.status === "canceled") {
    el("btnClear").disabled = false;
  }
  const items = await fetch(`/api/tasks/${taskId}/items`).then((r) => r.json());
  renderQueue(items.items);
  // If nothing selected, auto-select the first done item with md.
  if (!activeItemId) {
    const first = items.items.find((x) => x.status === "done" && x.mdFiles && x.mdFiles.length);
    if (first) await selectItem(first);
  }
  if (t.status === "done" || t.status === "failed" || t.status === "canceled") {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }
}

async function selectItem(item) {
  activeItemId = item.itemId || null;
  el("previewMeta").textContent = item.relpath || item.filename || "";
  el("btnCopy").disabled = true;
  el("mdPreview").textContent = "正在加载 Markdown…";
  el("tips").style.display = "none";
  renderQueue(await fetch(`/api/tasks/${taskId}/items`).then((r) => r.json()).then((x) => x.items));

  if (item.status !== "done") {
    el("mdPreview").textContent = item.status === "failed" ? (item.error || "识别失败") : "尚未完成";
    return;
  }
  if (!item.mdFiles || !item.mdFiles.length) {
    el("mdPreview").textContent = "该文件暂无 Markdown 输出（可能只有图片输出或仍在生成中）";
    return;
  }
  const resp = await fetch(`/api/tasks/${taskId}/items/${item.itemId}/md`);
  if (!resp.ok) {
    const text = await resp.text();
    el("mdPreview").textContent = `加载失败：${text}`;
    return;
  }
  const data = await resp.json();
  el("mdPreview").textContent = data.md || "";
  el("btnCopy").disabled = !(data.md && data.md.length);
}

async function start() {
  if (selected.length === 0) return;

  // Disallow starting a second task while one is active.
  if (taskId && (lastTaskStatus === "running" || lastTaskStatus === "queued")) {
    setStatus("当前任务仍在执行中，请先停止或等待完成");
    return;
  }

  const fd = new FormData();
  const relpaths = [];
  for (const f of selected) {
    fd.append("files", f.file, f.file.name);
    relpaths.push(f.relpath || f.file.name);
  }
  fd.append("relpaths", JSON.stringify(relpaths));
  fd.append("force_async", el("optForceAsync").checked ? "true" : "false");
  fd.append("use_doc_orientation_classify", el("optOrientation").checked ? "true" : "false");
  fd.append("use_doc_unwarping", el("optUnwarp").checked ? "true" : "false");
  fd.append("use_chart_recognition", el("optChart").checked ? "true" : "false");

  setStatus("正在提交任务…");
  const resp = await fetch("/api/tasks", { method: "POST", body: fd });
  if (!resp.ok) {
    const text = await resp.text();
    setStatus(`提交失败：${text}`);
    return;
  }
  const data = await resp.json();
  taskId = data.taskId;
  el("btnRefresh").disabled = false;
  el("btnDownload").disabled = true;
  el("btnStop").disabled = false;
  setStatus(`任务已创建：${taskId}`);

  // This UI only supports one active task at a time.
  selected = [];
  el("btnStart").disabled = true;
  el("btnClear").disabled = true;

  await refreshTask();
  pollTimer = setInterval(refreshTask, 1200);
}

async function stop() {
  if (!taskId) return;
  el("btnStop").disabled = true;
  try {
    const resp = await fetch(`/api/tasks/${taskId}/cancel`, { method: "POST" });
    if (!resp.ok) {
      const text = await resp.text();
      setStatus(`停止失败：${text}`);
      el("btnStop").disabled = false;
      return;
    }
    setStatus("已请求停止识别（尽快生效）");
    await refreshTask();
  } catch {
    setStatus("停止失败：网络错误");
    el("btnStop").disabled = false;
  }
}

function resetUI() {
  selected = [];
  taskId = null;
  activeItemId = null;
  lastTaskStatus = null;
  lastTaskTotal = 0;
  lastTaskDone = 0;
  lastTaskFailed = 0;
  lastTaskCanceled = 0;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  const list = el("queueList");
  list.classList.add("empty");
  list.innerHTML = `
    <div class="emptyState">
      <div class="emptyTitle">还没有文件</div>
      <div class="emptyHint">把文件拖进来，或点击“选择文件/选择文件夹”。</div>
    </div>
  `;
  setStatus("未开始");
  el("btnStart").disabled = true;
  el("btnClear").disabled = true;
  el("btnRefresh").disabled = true;
  el("btnDownload").disabled = true;
  el("btnStop").disabled = true;
  el("btnCopy").disabled = true;
  el("previewMeta").textContent = "请选择一个已完成的文件";
  el("mdPreview").textContent = "（尚无内容）";
  el("tips").style.display = "block";
}

function clearAction() {
  // No task yet: clear selection and reset.
  if (!taskId) {
    resetUI();
    return;
  }

  // Task finished: reset whole UI.
  if (lastTaskStatus === "done" || lastTaskStatus === "failed" || lastTaskStatus === "canceled") {
    resetUI();
    return;
  }

  // Task running/queued: only clear pending local selection.
  selected = [];
  el("btnStart").disabled = true;
  el("btnClear").disabled = true;
  setStatus("已清空待上传文件（不影响正在执行的任务）");
}

function addSelectedFiles(items) {
  // If a task is active, don't mix in new local selections.
  if (taskId && lastTaskStatus && !(lastTaskStatus === "done" || lastTaskStatus === "failed" || lastTaskStatus === "canceled")) {
    setStatus("当前任务进行中，无法追加新文件；请等待完成或点击“停止识别”后再开始新任务");
    return;
  }

  let ignored = 0;
  for (const it of items) {
    const f = it.file;
    const rel = it.relpath || (f.webkitRelativePath || f.name);
    if (!isSupportedFile(f)) {
      ignored += 1;
      continue;
    }
    selected.push({ file: f, relpath: rel });
  }

  el("btnStart").disabled = selected.length === 0;
  el("btnClear").disabled = selected.length === 0;
  renderQueue(
    selected.map((x) => ({
      filename: x.file.name,
      relpath: x.relpath,
      size: x.file.size,
      status: "queued",
      error: "",
    }))
  );

  if (selected.length === 0 && ignored > 0) {
    setStatus(`已忽略 ${ignored} 个不支持的文件格式（仅支持图片与 PDF）`);
  } else if (ignored > 0) {
    setStatus(`已选择 ${selected.length} 个文件（已忽略 ${ignored} 个不支持格式），点击“开始识别”`);
  } else {
    setStatus(`已选择 ${selected.length} 个文件，点击“开始识别”`);
  }
}

function addFiles(fileList) {
  addSelectedFiles(Array.from(fileList).map((f) => ({ file: f, relpath: f.webkitRelativePath || f.name })));
}

async function getDroppedFiles(dt) {
  if (!dt) return [];
  const items = dt.items;
  if (items && items.length && items[0].webkitGetAsEntry) {
    const entries = [];
    for (const item of items) {
      const entry = item.webkitGetAsEntry();
      if (entry) entries.push(entry);
    }
    const out = [];

    async function readAllEntries(dirEntry) {
      const reader = dirEntry.createReader();
      const all = [];
      while (true) {
        const batch = await new Promise((resolve) => reader.readEntries(resolve));
        if (!batch || batch.length === 0) break;
        all.push(...batch);
      }
      return all;
    }

    async function walk(entry) {
      if (entry.isFile) {
        const file = await new Promise((resolve) => entry.file(resolve));
        const relpath = (entry.fullPath || `/${file.name}`).replace(/^\//, "");
        out.push({ file, relpath });
        return;
      }
      if (entry.isDirectory) {
        const children = await readAllEntries(entry);
        for (const child of children) {
          await walk(child);
        }
      }
    }

    for (const entry of entries) {
      await walk(entry);
    }
    return out;
  }

  if (dt.files && dt.files.length) {
    return Array.from(dt.files).map((f) => ({ file: f, relpath: f.webkitRelativePath || f.name }));
  }
  return [];
}

function wire() {
  el("btnPickFiles").addEventListener("click", () => el("fileInput").click());
  el("btnPickFolder").addEventListener("click", () => el("folderInput").click());

  el("fileInput").addEventListener("change", (e) => {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = "";
  });
  el("folderInput").addEventListener("change", (e) => {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = "";
  });

  el("btnStart").addEventListener("click", start);
  el("btnStop").addEventListener("click", stop);
  el("btnClear").addEventListener("click", clearAction);
  el("btnRefresh").addEventListener("click", refreshTask);
  el("btnDownload").addEventListener("click", () => {
    if (!taskId) return;
    window.location.href = `/api/tasks/${taskId}/download.zip`;
  });

  el("btnCopy").addEventListener("click", async () => {
    const text = el("mdPreview").textContent || "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      el("btnCopy").textContent = "已复制";
      setTimeout(() => (el("btnCopy").textContent = "复制 Markdown"), 900);
    } catch {
      // fallback: do nothing
    }
  });

  const dz = el("dropZone");
  dz.addEventListener("dragover", (e) => {
    e.preventDefault();
    dz.classList.add("dragover");
  });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("dragover");
    const dt = e.dataTransfer;
    if (!dt) return;
    getDroppedFiles(dt).then((items) => {
      if (!items || items.length === 0) return;
      addSelectedFiles(items);
    });
  });
}

wire();
resetUI();
