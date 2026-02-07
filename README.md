## PaddleOCR-VL-1.5 Web UI

* 后台直接使用 [Baidu AI Studio](https://aistudio.baidu.com/paddleocr) 提供的 [Access Token](https://aistudio.baidu.com/account/accessToken) 和 API 接口。
* 支持：图片、PDF；支持批量 OCR。
* 输出会按任务写入 `output/{task_id}/...`，也可在页面上下载 ZIP。
* **本工具使用 AI 生成。**

### 使用说明

1. 克隆到本地，然后运行 `uv sync` 安装依赖。
2. 从 [Baidu AI Studio](https://aistudio.baidu.com/paddleocr) 获取自己的 API KEY 和 API URL，填到 `.env` 文件中。
3. PowerShell 进入项目文件夹，运行 `uv run python -m app`。Windows 环境也可直接运行 `run.bat`。

### 更新日志

#### 2026-02-07

* 新增本机 Web UI：`uv run python -m app` 启动。

* 后端改为服务端持有 Token：仅从 `.env` 读取 `BAIDU_AI_STUDIO_API_KEY`，前端不显示/不传递 Token。

* 支持图片/PDF 批量上传与拖放；拖放文件夹在 Chromium 系浏览器递归展开目录内容。

* 前后端双重过滤：仅接受图片与 PDF，避免不支持格式导致识别报错。

* 新增任务队列与状态轮询：展示等待/识别中/完成/失败；支持下载任务输出 ZIP。

* 新增“停止识别”：对当前任务发起取消请求，尽快停止后续文件/轮询（单次网络请求可能无法立刻中断）。

* 输出目录结构调整：上传文件直接落盘到 `output/{task_id}/inputs/...`，不再生成重复的 `_uploads/`。

* 文件名/路径展示优化：UI 展示保留原始相对路径（含中文），同时落盘路径仍做安全清理。

* 预览与排版优化：

  * 队列文件名按容器宽度自适应省略；悬停显示完整路径。

  * 右侧状态/大小固定宽度不换行。

  * Markdown 预览长行自动换行，避免撑破布局。

  * 提示符 ⓘ 字体优化与提示信息位置调整。

* 多页 PDF 增加合并结果：异步 PDF 识别后在 `output/{task_id}/{item_id}/merged.md` 生成合并 Markdown（页间用 `---` 分隔），预览默认显示合并版。
