# 使用 Python 3.13 官方镜像作为基础
FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 安装 uv 包管理器
RUN pip install uv --no-cache-dir

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 复制依赖配置文件
COPY pyproject.toml uv.lock ./

# 使用 uv 安装依赖
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY app ./app

# 复制并设置入口脚本
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 创建非 root 用户（安全最佳实践）
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# 暴露端口（仅作为文档）
EXPOSE 22438

# 设置入口点
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
