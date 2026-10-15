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

## 本机 Docker Desktop Kubernetes（第一期）

适合：本机已启用 Docker Desktop → Kubernetes，先跑通 **web + api + mysql + redis + holmes**（不开沙箱 / 不开 ttyd）。

### 准备

1. `kubectl config use-context docker-desktop` 且 `kubectl get nodes` 为 Ready。
2. 构建业务镜像（与 YAML 中名字一致）：

```powershell
cd D:\LangChain_Demo
$env:SANDBOX_WORKSPACE_HOST="D:/LangChain_Demo/data/sandbox"
docker compose build --pull=false api nginx
```

3. 精简 Secret（**不要**用整份 `.env`，易重复键 / 键名带空格）：

```powershell
# 方式 A：从根目录 .env 抽出所需键（推荐本机已有 .env 时）
python deploy/k8s/_gen_env_k8s.py

# 方式 B：手工复制模板再填值
# Copy-Item deploy\k8s\env.k8s.example deploy\k8s\env.k8s
# KEY=value，等号两边无空格；每个键只一行

kubectl apply -f deploy/k8s/00-namespace.yaml
kubectl -n nexora delete secret nexora-secret --ignore-not-found
kubectl -n nexora create secret generic nexora-secret --from-env-file=deploy/k8s/env.k8s
```

4. 应用清单并观察：

```powershell
kubectl apply -f deploy/k8s/
kubectl -n nexora get pods -w
```

5. 前端入口：**http://localhost:8080**（不要用 `:80`）。

```powershell
curl.exe http://127.0.0.1:8080/health
```

### 已知坑

| 现象 | 原因 | 处理 |
|------|------|------|
| mysql Crash，日志含 `MYSQL_USER="root"` | 官方镜像禁止用 `MYSQL_USER` 配置 root | `20-mysql.yaml` 只保留 `MYSQL_ROOT_PASSWORD` + `MYSQL_DATABASE` |
| holmes `HOLMES_PORT=tcp://...` ValueError | Service 名 `holmes` 注入 Docker-link 风格环境变量 | `enableServiceLinks: false` + `HOLMES_PORT=5050` |
| 浏览器打开 localhost 是 Welcome to nginx | WSL/本机 nginx 占 `127.0.0.1:80` | web Service 映射 **8080** |
| `create secret` 报 duplicate / invalid key | `.env` 重复键或 `KEY ` 带空格 | 用 `deploy/k8s/env.k8s`，键名去空格、去重 |
| Memory / 混合召回静默降级 | 未注入 `EMBEDDING_*` | `env.k8s` + `40-api.yaml` 已要求这三项 |
| 日志里 AUTH_DEBUG / OpenAPI 警告 | 镜像默认偏松 | `40-api.yaml` 已显式 `AUTH_DEBUG_ENABLED=false`、`OPENAPI_ENABLED=false` |

### 改配置后滚动

```powershell
kubectl -n nexora delete secret nexora-secret --ignore-not-found
kubectl -n nexora create secret generic nexora-secret --from-env-file=deploy/k8s/env.k8s
kubectl apply -f deploy/k8s/40-api.yaml
kubectl -n nexora rollout restart deploy/api
```

上云时把 `STRICT_PRODUCTION` 改为 `"true"`，并按生产要求收紧 CORS / 管理员口令等（见上文 Compose 生产开关）。
