# ===== 阶段 1：构建前端（必须拷贝 frontend 源码，不要 ignore 掉）=====
FROM node:20-bookworm-slim AS frontend
WORKDIR /fe

# 跳过 Electron 二进制下载（Web 镜像不需要桌面端）
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 整份前端源码进构建上下文（src / public / vite.config 等）
COPY frontend/ ./

# 同源反代 /api，构建时不要写死内网 8020（等号两边不能有空格）
ENV VITE_API_BASE=
RUN npm run build

# ===== 阶段 2：API =====
FROM python:3.12-slim AS api
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 bsdutils \
    && rm -rf /var/lib/apt/lists/*
# ttyd：交互终端
ARG TTYD_VERSION=1.7.7
RUN curl -fsSL -o /usr/local/bin/ttyd \
      "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.x86_64" \
    && chmod +x /usr/local/bin/ttyd
# 使用国内镜像进行加速构建镜像
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r api-requirements.txt

COPY api/ ./api/
COPY application/ ./application/
COPY agents/ ./agents/
COPY billing/ ./billing/
COPY config/ ./config/
COPY infrastructure/ ./infrastructure/
COPY memory/ ./memory/
COPY observability/ ./observability/
COPY rag/ ./rag/
COPY safety/ ./safety/
COPY shared/ ./shared/
COPY skills/ ./skills/
COPY utils/ ./utils/
COPY domain/ ./domain/
COPY orchestration/ ./orchestration/
COPY e2e/ ./e2e/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8020
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8020", "--workers", "1"]

# ===== 阶段 3：Nginx 静态站（前端产物打进镜像，避免空卷盖住文件）=====
FROM nginx:1.27-alpine AS web
COPY --from=frontend /fe/dist /usr/share/nginx/html
COPY deploy/nginx.docker.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
