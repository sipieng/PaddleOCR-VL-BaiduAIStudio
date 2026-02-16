#!/bin/bash
# Docker 入口脚本 - 支持环境变量配置

set -e

# 从环境变量读取配置，使用默认值
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-22438}"

# 修复 output 目录权限（以 root 用户运行）
if [ -d "/app/output" ]; then
    echo "Fixing permissions for /app/output..."
    chown -R appuser:appuser /app/output
    chmod -R 755 /app/output
fi

# 创建 output 目录（如果不存在）
if [ ! -d "/app/output" ]; then
    echo "Creating /app/output directory..."
    mkdir -p /app/output
    chown -R appuser:appuser /app/output
    chmod 755 /app/output
fi

echo "Starting PaddleOCR-VL on ${HOST}:${PORT}"

# 使用 gosu 以非 root 用户启动应用
exec gosu appuser uv run uvicorn app.server:app --host "$HOST" --port "$PORT"
