# 云上部署（2 核 2G）

## Docker Compose（推荐）

1. 加 2G swap。
2. 复制 `.env.production.example` 为 `.env`，填写密钥；`REDIS_URL` 在 compose 里会覆盖为 `redis://redis:6379/0`。
3. 在仓库根目录：`docker compose up -d --build`
4. 安全组只开 80/443，不要映射 8020 / 6379。
5. 生产开关：`AUTH_ENABLED=true`、`STRICT_PRODUCTION=true`、`AUTH_DEBUG_ENABLED=false`、`OPENAPI_ENABLED=false`。

前端源码在 `frontend/`，由 `Dockerfile` 的 frontend 阶段构建后打进 `web`（nginx）镜像；**不要**在 `.dockerignore` 里排除 `frontend/src` 等源码。

## 传统部署（无 Docker）

1. 加 2G swap。
2. 安装 Redis，并确保只监听 `127.0.0.1`。
3. 克隆仓库，创建 venv，`pip install -r requirements.txt`。
4. 复制 `.env.production.example` 为 `.env` 并填写密钥。
5. `cd frontend && npm ci && npm run build`，把 `dist` 拷到 Nginx `root`。
6. 安装 systemd 单元：`deploy/langchain-api.service`（改路径）。
7. 使用 `deploy/nginx.conf`：安全组只开 80/443，**不要**暴露 8020。
8. HTTPS：`sudo apt install certbot python3-certbot-nginx` 后执行  
   `sudo certbot --nginx -d your.domain.example`  
   （先把配置里的域名换成真实域名）。
9. 生产开关必须为：  
   `AUTH_ENABLED=true`、`STRICT_PRODUCTION=true`、`AUTH_DEBUG_ENABLED=false`、  
   `OPENAPI_ENABLED=false`、`RATE_LIMIT_BACKEND=redis`、`TRUST_PROXY=true`。

首次启动会把 `ADMIN_USERNAME` / `ADMIN_PASSWORD` **哈希后写入** MySQL `users` 表（`AUTH_BACKEND=mysql`）。之后改环境变量不会自动改库内密码，除非设 `AUTH_BOOTSTRAP_RESET_ADMIN=true` 再重启一次。`.env` 里需要有 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`；Compose 会把 `MYSQL_HOST` 覆盖为服务名 `mysql`。

前端构建：同源反代 `/api` 时 `VITE_API_BASE` 可留空或设为 `https://你的域名`。

## 自动部署（GitHub Actions）

生产机不要装 Jenkins。推送 `main` 后由 Actions SSH 执行 `deploy/update.sh`。

1. 在服务器把脚本设为可执行：`chmod +x /opt/LangChain_Demo/deploy/update.sh`
2. GitHub 仓库 Secrets：`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`
3. **先本地 / 服务器手工测脚本，确认没问题再 push workflow**

本地（Git Bash / WSL，且本机已能 `docker compose`）：

```bash
# 只检查脚本语法
bash -n deploy/update.sh

# 不拉 GitHub、不 reset，只按当前目录重建容器
APP_DIR="$(pwd)" SKIP_GIT=1 bash deploy/update.sh
```

服务器（会 `git reset --hard` 到远程 `main`，`.env` 不受影响）：

```bash
bash /opt/LangChain_Demo/deploy/update.sh
```
