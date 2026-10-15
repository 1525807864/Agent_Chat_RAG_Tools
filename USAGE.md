# Nexora 使用文档

面向本地开发、联调与日常使用的操作说明。产品总览与架构见 [README.md](README.md)；云上部署见 [deploy/README.md](deploy/README.md)。

---

## 目录

1. [环境准备](#1-环境准备)
2. [本地启动](#2-本地启动)
3. [登录与门户](#3-登录与门户)
4. [对话平台](#4-对话平台)
5. [知识库与 RAG](#5-知识库与-rag)
6. [自动测试工作台](#6-自动测试工作台)
7. [平台沙箱](#7-平台沙箱)
8. [运维工作台](#8-运维工作台)
9. [Electron 桌面端](#9-electron-桌面端)
10. [HTTP API 速查](#10-http-api-速查)
11. [健康检查与就绪](#11-健康检查与就绪)
12. [常见问题](#12-常见问题)

---

## 1. 环境准备

| 组件 | 要求 |
|------|------|
| Python | 3.11+（推荐 3.12 / 3.13） |
| Node.js | 18+ |
| LLM Key | DeepSeek / OpenAI 兼容协议均可 |
| 可选 | Redis、MySQL 8、Docker、npx（Playwright） |

### 1.1 安装依赖

```bash
# 仓库根目录
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
pip install -r api/requirements.txt   # 若与主依赖分离安装

cd frontend
npm install
cd ..
```

### 1.2 配置 `.env`

```bash
copy .env.example .env    # Windows
# cp .env.example .env    # macOS / Linux
```

**本地最小可用示例：**

```env
DEEPSEEK_API_KEY=sk-你的密钥
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
OPENAPI_ENABLED=true
ALLOW_REGISTER=true
```

说明：

- `AUTH_ENABLED=false`：本地可免登录直进（仍建议联调时打开鉴权）。
- `AUTH_BACKEND=sqlite`：无需本机 MySQL；生产 Compose 使用 MySQL。
- RAG / 嵌入另需 `EMBEDDING_API_*`（见 `.env.example`）。
- 完整变量说明见 [README.md 配置要点](README.md#配置要点) 与 `.env.example`。

---

## 2. 本地启动

请开**两个终端**（或使用 IDE 任务）。

### 2.1 后端（端口 8020）

```bash
# 仓库根目录，已激活 venv
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

成功标志：日志出现 `Application startup complete` / `Uvicorn running on http://127.0.0.1:8020`。

### 2.2 前端（端口 5173）

```bash
cd frontend
npm run dev
```

浏览器打开：`http://127.0.0.1:5173`。

可选：在 `frontend/.env` 中指定后端地址：

```env
VITE_API_BASE=http://127.0.0.1:8020
```

不填时，Electron 默认走 8020；纯网页开发也建议显式写上，避免代理混淆。

### 2.3 同时启动桌面端（可选）

```bash
cd frontend
# 会拉起 Vite + Electron；若 Electron 还会起后端，注意勿与已有 8020 冲突
npm run dev:desktop

# 后端已手动启动时：
npm run dev:desktop:no-api
```

### 2.4 CLI（可选）

```bash
python main.py
```

---

## 3. 登录与门户

1. 打开前端地址。
2. 若 `AUTH_ENABLED=true`：使用注册 / 登录（默认可注册，见 `ALLOW_REGISTER`）。  
   管理员首次可由 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 引导写入用户库。
3. 登录后进入 **工作台门户**（hash `#/`）。

| 领域 | 路由 / 工作区 | 状态 |
|------|----------------|------|
| 对话平台 | `#/chat` | 已上线 |
| 自动测试平台 | `#/qa` | 已上线 |
| 运维排障 | `#/ops`（若门户已挂载） | 已上线（依赖配置） |
| 其它卡片 | — | 「即将开放」占位 |

顶栏可返回「工作台首页」。设置面板可填写本轮 **API Key / Base / Model**（留空则用服务端 `.env`）。

---

## 4. 对话平台

### 4.1 选择模式

在 Mode 栏选择：

| mode | 适用场景 |
|------|----------|
| `chat` | 日常问答；会话记忆 + Solip；SSE 真流式 |
| `rag` | 基于已建知识库的问答 |
| `consult` | 结构化咨询：先补全因子再检索 |
| `graph-rag` | 向量 + 知识图谱增强 |
| `agent` | 需要工具（搜索、读文件、工作区、MCP 等） |
| `multi` | 多智能体：sequential / debate / router |

### 4.2 推荐操作流

1. **chat**：直接提问；长会话会触发摘要压缩与 Solip「下一问」预测。  
2. **rag / graph-rag**：先在知识库面板上传文档并建库，再提问。  
3. **agent**：  
   - 需要实时搜索时配置 `TAVILY_API_KEY`；  
   - 桌面端可「打开工作区」注入本地文件工具；  
   - `MCP_SERVERS_JSON` 可挂外部 MCP（如 Playwright）。  
4. **流式**：默认走 `POST /api/chat/stream`；可在界面关闭流式改走整包 `/api/chat`。

### 4.3 Skills

对话中可使用 Skills 约定（如 `/skill`，具体以当前 Skills 运行时为准）。技能文件目录见 `data/skills/`、`skills/` 包。

### 4.4 会话

- 左侧会话列表：拉取 `/api/sessions`、加载历史 `/api/sessions/{id}`。  
- 记忆快照：`GET /api/sessions/{id}/memory`（摘要、Solip 下一问等）。

---

## 5. 知识库与 RAG

1. 在对话台打开知识库相关面板。  
2. 上传文档到租户目录（`POST /api/knowledge/docs/upload`）。  
3. 同步建库：`POST /api/knowledge/build`；或异步：`/build/async` 后轮询 `/build/{job_id}`。  
4. 切换到 `rag` / `graph-rag` / `consult` 提问。

依赖：

```env
EMBEDDING_API_BASE=...
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
HYBRID_RETRIEVAL_ENABLED=true
```

图谱统计：`GET /api/knowledge/graph/stats`。

---

## 6. 自动测试工作台

入口：门户 → **自动测试平台**（`#/qa`）。

典型流程：

1. 创建 / 选择项目。  
2. 配置来源（文档 / 接口说明等）。  
3. 生成或维护用例树。  
4. 确认用例后发起运行（含 UI 运行 `/runs/ui`，依赖 Playwright MCP / npx）。  
5. 查看 runs、导出报告、管理成员权限。  
6. 可用项目内「助手」对话辅助写用例（`/assistant`）。

主要 API 前缀：`/api/qa/*`（见下文速查）。

---

## 7. 平台沙箱

用于在隔离容器中执行 shell / pwsh / 工作区文件操作；高危命令可前端审批。

### 7.1 启用

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

构建镜像：

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

### 7.2 使用注意

- 本机需可用 Docker。  
- Compose 部署时 `SANDBOX_WORKSPACE_HOST` 必须是**宿主机绝对路径**。  
- 审批面板：`frontend/src/components/sandbox/`。

API：`/api/sandbox/sessions` 及 shell / exec / fs 子路径。

---

## 8. 运维工作台

入口：门户中的运维领域（`OpsWorkspace`）。

能力分两块（均需对应开关）：

### 8.1 Holmes 问诊（HTTP 转发）

```env
HOLMES_ENABLED=true
HOLMES_API_BASE=http://127.0.0.1:5050
```

- 健康：`GET /api/ops/health`  
- 提问：`POST /api/ops/ask`  

Nexora 只转发，不内嵌 Holmes 源码。

### 8.2 交互终端（ttyd）

```env
OPS_TTYD_ENABLED=true
SANDBOX_ENABLED=true          # 通常依赖沙箱
OPS_TTYD_RUNTIME=native       # Windows 开发可试 wsl
OPS_TTYD_BIN=ttyd             # 或 tools/ttyd.exe / WSL 路径
```

创建会话后前端嵌入终端视图；注意 `OPS_TTYD_ALLOWED_ORIGINS` 需包含前端 Origin。

---

## 9. Electron 桌面端

```bash
cd frontend
npm run dist          # 打 Windows 安装包，产物在 frontend/release
```

特性摘要：

- 可自动拉起本机 API（可用 `ELECTRON_START_BACKEND=0` 关闭）。  
- 划词解释、工作区文件工具、安装包下载接口（`/api/downloads/desktop`）。  

生产下载：配置 `DESKTOP_DOWNLOAD_ENABLED`、`DESKTOP_RELEASE_DIR` 等。

---

## 10. HTTP API 速查

基址默认：`http://127.0.0.1:8020`。  
`AUTH_ENABLED=true` 时除健康检查外需：

```http
Authorization: Bearer <access_token>
```

### 10.1 登录

```bash
curl -s http://127.0.0.1:8020/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"your-password\"}"
```

（具体路径以 `api/routes/auth_login.py` 挂载前缀为准，一般为 `/api/auth/login`。）

### 10.2 对话

```bash
# 非流式
curl -s http://127.0.0.1:8020/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d "{\"message\":\"你好\",\"mode\":\"chat\",\"session_id\":\"demo\"}"

# 流式 SSE
curl -N http://127.0.0.1:8020/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d "{\"message\":\"你好\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

`mode`：`chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`。

### 10.3 主要前缀

| 前缀 | 说明 |
|------|------|
| `/api/auth/*` | 登录 / 注册 |
| `/api/chat` · `/api/chat/stream` | 对话 |
| `/api/sessions/*` | 会话列表、历史、记忆、删除 |
| `/api/knowledge/*` | 文档、建库、图谱统计 |
| `/api/qa/*` | 测试项目 / 用例 / 运行 / 成员 |
| `/api/sandbox/*` | 沙箱会话与执行 |
| `/api/ops/*` | Holmes 运维问诊 |
| `/api/ops/terminal/*` | ttyd 终端会话 |
| `/api/billing/*` | 用量查询 / flush |
| `/api/downloads/*` | 桌面安装包 |
| `/health` · `/health/live` · `/health/ready` | 探活 / 就绪 |

交互式文档（非生产且 `OPENAPI_ENABLED=true`）：`http://127.0.0.1:8020/docs`。

---

## 11. 健康检查与就绪

| 接口 | 含义 |
|------|------|
| `GET /health` 或 `/health/live` | 进程存活（liveness） |
| `GET /health/ready` | 业务就绪（readiness）；失败返回 503 |

前端启动会轮询 `/health/ready`，未就绪时业务接口可能被中间件拦截（503）。

本地自检：

```bash
curl -s http://127.0.0.1:8020/health/live
curl -s http://127.0.0.1:8020/health/ready
```

---

## 12. 常见问题

### 前端显示「API 未就绪 / 不可用」

- 确认后端已在 8020 监听。  
- 检查 `VITE_API_BASE` 或 Electron `LANGCHAIN_API_BASE`。  
- 查看 `/health/ready` 的 `checks` 与 `startup_error`。

### 端口占用（Windows 10048）

旧 uvicorn / Electron 仍占 8020。结束占用进程后重启，或改端口并同步前端 Base。

### 加载历史提示「请求过于频繁」

全站 API 限流默认已关闭；仅登录 / 注册仍按 `LOGIN_RATE_LIMIT` 限流。若仍出现，确认是否跑的是最新后端代码。

### Agent 不联网搜索

- 配置 `TAVILY_API_KEY`。  
- 使用 `mode=agent`（chat 模式不会调搜索工具）。  
- SSL 问题时本地可临时 `SEARCH_SSL_VERIFY=false`（仅开发）。

### RAG 无结果 / 嵌入失败

- 核对 `EMBEDDING_API_*` 与模型名。  
- 确认已对正确租户上传文档并完成 build。

### Tool calling / DeepEval 报 `bind_tools` NotImplementedError

评测与原生 tool calling 请使用 `infrastructure.llm.openai_compat.create_chat_openai`（ChatOpenAI + DeepSeek Base），不要直接用未实现 `bind_tools` 的 `DeepSeekChatModel`。

### Docker Compose 生产

见 [deploy/README.md](deploy/README.md)：安全组只开 80/443，`AUTH_ENABLED=true`，`STRICT_PRODUCTION=true`，`OPENAPI_ENABLED=false`。

---

## 13. 日志与排错

应用启动时会配置统一日志：

| 输出 | 位置 |
|------|------|
| 控制台 | uvicorn / 终端 |
| 轮转文件 | `data/app.log`（约 10MB × 5 份） |

常用 logger 名（便于 `grep`）：

- `nexora.startup` — 启停与就绪检查  
- `nexora.access` — HTTP 访问（method/path/status/耗时）  
- `nexora.chat` / `app.trace` — 对话与编排事件（含 `request_id`）  
- `nexora.auth` — 登录/注册（不含密码）  
- `nexora.qa` / `nexora.knowledge` — 测试台与建库  
- `infrastructure.llm.deepseek` — 模型调用成败与 token  

排错示例：

```bash
# Windows PowerShell
Get-Content data\app.log -Tail 80
Select-String -Path data\app.log -Pattern "ERROR|chat_stream_error|DeepSeek API"
```

响应头 `X-Request-Id` 与日志里的 `request_id=` 对应，可串起一整轮请求。

`LOG_LEVEL` 在 `.env` 中设置（默认 `INFO`）；需要更细时可改为 `DEBUG`。

---

## 相关文档

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 产品介绍、架构、快速开始摘要 |
| [deploy/README.md](deploy/README.md) | 云上 Compose / Nginx / Actions |
| `.env.example` | 全量环境变量模板 |
| `.env.production.example` | 生产模板 |

如有接口变更，以 `api/routes/` 与运行中的 `/docs` 为准。
