# Docker 部署指南

本文档说明如何使用 Docker 将 PaddleOCR-VL 项目部署到 VPS。

## 前置要求

- VPS 上已安装 Docker（Docker Compose v2 已内置）
- 百度 AI Studio 账号和 API Key

## 快速开始

### 1. 准备 VPS

如果 VPS 上未安装 Docker：

```bash
# 安装 Docker（包含 Docker Compose v2）
curl -fsSL https://get.docker.com | sh

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
docker compose version
```

### 2. 获取 API 配置

从 [百度 AI Studio](https://aistudio.baidu.com/paddleocr) 获取以下信息：
- **API KEY**：访问 https://aistudio.baidu.com/account/accessToken
- **同步解析 API URL**：类似 `https://xxxx.aistudio-app.com/layout-parsing`
- **异步解析 API URL**：`https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`

### 3. 配置环境变量

在 VPS 上创建 `.env` 文件（与 `docker-compose.yml` 同目录）：

```bash
# 百度 AI Studio 配置（必填）
BAIDU_AI_STUDIO_API_KEY=你的API_KEY
BAIDU_PADDLE_OCR_API_URL="https://你的API_ID.aistudio-app.com/layout-parsing"
BAIDU_PADDLE_OCR_JOB_URL="https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"

# 可选配置（Docker 部署端口）
HOST_PORT=22438              # 宿主机端口（外部访问的端口）
CONTAINER_PORT=22438         # 容器内端口（应用监听的端口）

# 可选配置（性能调优）
DEFAULT_CONCURRENCY=2        # 并发处理数
MAX_FILE_BYTES=26214400      # 单文件最大 25MB
MAX_TOTAL_BYTES=262144000    # 总上传最大 250MB

# 可选配置（资源限制）
CPUS_LIMIT=2                 # CPU 上限
MEMORY_LIMIT=2G              # 内存上限
CPUS_RESERVATION=0.5         # CPU 预留
MEMORY_RESERVATION=512M      # 内存预留

# 可选配置（日志）
LOG_MAX_SIZE=10m             # 单个日志文件最大 10MB
LOG_MAX_FILE=3               # 保留最近 3 个日志文件
```

**说明**：
- `.env` 文件会被 `docker compose` 自动读取
- 所有配置都有默认值，可以只填必需的 API 配置
- 同一份 `.env` 文件可以同时支持本地开发和 Docker 部署

⚠️ **重要**：
- 不要将包含真实 API Key 的 `.env` 文件提交到 Git 仓库
- `.env` 文件已加入 `.gitignore`

### 4. 构建并启动

```bash
# 克隆项目（如果还没有）
git clone <your-repo-url>
cd PaddleOCR-VL-BaiduAIStudio

# 构建镜像
docker compose build

# 启动服务
docker compose up -d
```

### 5. 验证部署

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f

# 测试服务
curl http://localhost:22438/
```

如果一切正常，你应该看到 HTML 页面内容。

## 常用命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看日志
docker compose logs -f paddleocr-vl

# 更新并重启
docker compose pull
docker compose up -d

# 进入容器
docker compose exec paddleocr-vl bash

# 清理旧镜像
docker image prune -a -f

# 重新构建镜像（无缓存）
docker compose build --no-cache
```

## 配置说明

### 端口配置

默认使用端口 **22438**。如需修改，编辑 `.env` 文件：

```bash
# 修改宿主机端口（外部访问端口）
HOST_PORT=8080

# 修改容器内端口（应用监听端口，通常保持默认）
CONTAINER_PORT=22438
```

或者命令行覆盖：

```bash
HOST_PORT=8080 docker compose up -d
```

### 资源限制

默认资源限制（`.env` 中配置）：
- CPU：最大 2 核，保留 0.5 核
- 内存：最大 2GB，保留 512MB

根据 VPS 配置调整 `.env` 文件：

```bash
# 小型 VPS（1GB RAM）
CPUS_LIMIT=1
MEMORY_LIMIT=1G

# 大型 VPS（8GB RAM）
CPUS_LIMIT=4
MEMORY_LIMIT=4G
```

**资源限制的作用：**
- **limits（上限）**：防止容器占用过多资源，影响其他服务
- **reservations（预留）**：确保容器有足够资源正常运行
- 生产环境建议设置，开发环境可以省略

### 持久化存储

所有 OCR 输出文件存储在 Docker volume `output-data` 中。

查看/备份 volume：

```bash
# 查看 volume
docker volume ls

# 查看 volume 详情
docker volume inspect paddleocrvl-baiduaistudio_output-data

# 备份 volume
docker run --rm -v paddleocrvl-baiduaistudio_output-data:/data -v $(pwd):/backup ubuntu tar czf /backup/output-backup-$(date +%Y%m%d).tar.gz /data
```

### 并发控制

调整并发处理数，编辑 `.env` 文件：

```bash
DEFAULT_CONCURRENCY=4  # 增加并发数
```

## 工作原理

### docker-entrypoint.sh 的作用

**docker-entrypoint.sh 是容器启动时自动执行的脚本，你不需要手动运行它！**

**为什么需要它？**

Dockerfile 中无法直接在 `CMD` 中使用环境变量：

```dockerfile
# ❌ 这样写无法使用环境变量！
CMD ["uv", "run", "uvicorn", "app.server:app", "--port", "22438"]
#                                    ↑ 端口硬编码，无法读取 $PORT
```

**解决方案：使用 ENTRYPOINT 脚本**

```dockerfile
# ✅ 正确做法
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
```

脚本可以读取环境变量，然后动态启动应用：

```bash
#!/bin/bash
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-22438}"

exec uv run uvicorn app.server:app --host "$HOST" --port "$PORT"
```

### Docker 自动执行流程

```bash
# 1. 你执行这个命令
docker compose up -d

# 2. Docker 自动执行：
#    - 读取 .env 文件
#    - 构建镜像
#    - 创建容器
#    - 自动执行 ENTRYPOINT 指定的脚本
#    - 脚本读取环境变量（PORT、HOST 等）
#    - 启动应用

# 3. 你不需要：
#    ❌ 手动运行 docker-entrypoint.sh
#    ❌ 修改任何脚本
#    ❌ 手动设置环境变量到容器内
```

### 环境变量优先级

从高到低：

1. **命令行覆盖**：`HOST_PORT=8080 docker compose up -d`
2. **docker-compose.yml environment**：直接在 YAML 中设置
3. **.env 文件**：自动读取
4. **Dockerfile ENV**：镜像中的默认值

示例：

```bash
# .env 文件
PORT=9000

# docker-compose.yml
environment:
  - PORT=8000  # ✅ 最高优先级，覆盖 .env 的 9000
```

### docker-entrypoint.sh 与环境变量的配合

| 组件 | 作用 | 读取方式 |
|------|------|---------|
| `.env` 文件 | 存储配置（API Key、端口等） | docker compose 自动读取 |
| `docker-compose.yml` | 传递环境变量到容器 | `${VAR_NAME}` 语法 |
| `docker-entrypoint.sh` | 读取环境变量，启动应用 | `$VAR_NAME` 变量 |
| 应用（uvicorn） | 使用配置值 | 从环境变量读取 |

## Nginx 反向代理配置（推荐）

使用 Nginx 作为反向代理，添加 SSL 支持。

### 安装 Nginx

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx

# CentOS/RHEL
sudo yum install nginx certbot python3-certbot-nginx
```

### Nginx 配置

创建配置文件 `/etc/nginx/sites-available/paddleocr-vl`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 反向代理到 Docker 容器
    location / {
        proxy_pass http://127.0.0.1:22438;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置（处理大文件上传）
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 文件上传大小限制
    client_max_body_size 500M;
}
```

### 启用配置并获取 SSL 证书

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/paddleocr-vl /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx

# 获取 SSL 证书（会自动配置 HTTPS）
sudo certbot --nginx -d your-domain.com
```

## 故障排查

### 容器无法启动

```bash
# 查看详细日志
docker compose logs paddleocr-vl

# 检查环境变量
docker compose exec paddleocr-vl env | grep BAIDU

# 查看容器状态
docker compose ps -a
```

### 端口冲突

```bash
# 检查端口占用
sudo netstat -tlnp | grep 22438

# 修改 .env 文件中的 HOST_PORT
HOST_PORT=8080 docker compose up -d
```

### 权限问题

```bash
# 检查 volume 权限
docker compose exec paddleocr-vl ls -la /app/output

# 修复权限（如需要）
docker compose exec paddleocr-vl chown -R appuser:appuser /app/output
```

### 无法访问 API

```bash
# 检查容器网络连接
docker compose exec paddleocr-vl curl -v https://paddleocr.aistudio-app.com

# 检查防火墙规则
sudo ufw status
sudo ufw allow 22438
```

### 环境变量未生效

```bash
# 检查 .env 文件是否在正确位置
ls -la .env

# 验证环境变量语法
docker compose config

# 手动指定 .env 文件
docker compose --env-file .env.production up -d
```

## 安全建议

1. **使用强密码的 API Key**：不要使用弱密码
2. **启用 HTTPS**：使用 Let's Encrypt 免费 SSL 证书
3. **限制访问 IP**：在 Nginx 中添加 IP 白名单
4. **定期更新**：定期更新 Docker 镜像和系统
5. **监控日志**：定期检查 Docker 日志，发现异常访问

## 更新部署

```bash
# 拉取最新代码
git pull origin main

# 重新构建镜像
docker compose build --no-cache

# 重启服务
docker compose up -d

# 清理旧镜像
docker image prune -f
```

## 备份与恢复

### 备份

```bash
# 备份输出数据
docker run --rm -v paddleocrvl-baiduaistudio_output-data:/data -v $(pwd):/backup ubuntu tar czf /backup/output-$(date +%Y%m%d).tar.gz /data

# 备份配置文件
cp .env .env.backup
```

### 恢复

```bash
# 恢复输出数据
docker run --rm -v paddleocrvl-baiduaistudio_output-data:/data -v $(pwd):/backup ubuntu tar xzf /backup/output-$(date +%Y%m%d).tar.gz -C /

# 恢复配置文件
cp .env.backup .env
```

## 监控

### 查看资源使用

```bash
# 容器资源使用情况
docker stats paddleocr-vl

# 磁盘使用情况
df -h
docker system df

# 查看 volume 使用情况
docker system df -v | grep output-data
```

### 设置日志轮转

Docker 日志已通过 `.env` 文件配置轮转（默认值）：
- 单个日志文件最大 10MB
- 保留最近 3 个日志文件

可通过 `.env` 文件自定义：

```bash
LOG_MAX_SIZE=50m      # 单个日志文件最大 50MB
LOG_MAX_FILE=5        # 保留最近 5 个日志文件
```
