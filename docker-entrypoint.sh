#!/bin/bash
# Docker 入口脚本 - 支持环境变量配置

set -e

# 从环境变量读取配置，使用默认值
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-22438}"

echo "Starting PaddleOCR-VL on ${HOST}:${PORT}"

# 使用 uvicorn 启动应用
exec uv run uvicorn app.server:app --host "$HOST" --port "$PORT"
