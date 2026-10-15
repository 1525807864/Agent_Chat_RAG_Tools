<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**多模式 AI Agent 平台 · 对话 · RAG · 测试工作台 · 沙箱 · 运维**

[功能概览](#功能概览) · [快速开始](#快速开始本地) · [**使用文档**](USAGE.md) · [部署](deploy/README.md) · [License](LICENSE)

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/frontend-React%2018-61dafb)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/1525807864/Agent_Chat_RAG_Tools?display_name=tag)](https://github.com/1525807864/Agent_Chat_RAG_Tools/releases)

<br/>

**语言 / Languages**

[中文](README.md) · [English](README_en.md) · [日本語](README_ja.md) · [한국어](docs/i18n/README_ko.md) · [Español](docs/i18n/README_es.md)

</div>

---

基于 LangChain / LangGraph 的多模式 AI Agent 平台：普通对话、混合检索 RAG、结构化咨询、GraphRAG、ReAct 单 Agent（含 MCP）、多智能体协作；提供 FastAPI、Vite/React 前端（领域门户）、自动测试工作台、平台沙箱、运维排障（Holmes / ttyd），以及可选 Electron 桌面端。

默认 LLM 兼容 DeepSeek / OpenAI / 智谱等协议；可选 Cursor Agent SDK 处理改代码类请求。时间统一按 **Asia/Shanghai（北京时间）** 写入与展示。

> **日常怎么用？** 请阅读根目录完整操作手册 → **[USAGE.md](USAGE.md)**  
> （本地启动、各工作台、API 速查、健康检查、常见问题）

---

## 产品入口

登录后默认进入 **工作台门户**（hash `#/`）：

| 领域 | 状态 | 说明 |
|------|------|------|
| 对话平台 | 已上线 | `#/chat`，多模型 / RAG / Agent |
| 自动测试平台 | 已上线 | `#/qa`，用例 / 执行 / 报告 / UI Agent |
| 运维排障 | 已上线 | `#/ops`，Holmes 问诊 + ttyd 终端（需配置） |
| 代码评审、数据、知识库独立台等 | 占位 | 卡片「即将开放」，后续按垂直 Agent 接入 |

顶栏可「工作台首页」返回门户；对话与测试台视觉统一为 **墨色 + 香槟金** 风格。

---

## 功能概览

### 对话模式

| 模式 | 说明 |
|------|------|
| `chat` | 会话记忆（Memory / Solip）+ Skills（`/skill`）+ SSE 真流式 |
| `rag` | 稠密向量 + BM25 + RRF 混合检索，轻量查询路由 |
| `consult` | 因子补全追问后再混合检索 |
| `graph-rag` | 向量检索 + 知识图谱增强 |
| `agent` | ReAct 工具环；工作区读写；通用 MCP；可选主动工具发现；E2E Playwright |
| `multi` | sequential / debate / router 多智能体 |

### 平台能力

- **JWT 登录与租户**、知识库上传/建库、计费账本、登录限流与内容过滤  
- **启动就绪闭环**：`/health/live`（存活）+ `/health/ready`（就绪）+ 未就绪门闩  
- **自动测试工作台**：项目、用例、运行、报告导出、成员权限、项目知识库；UI Agent（Playwright）  
- **平台沙箱**（可选 Docker）：shell / pwsh / 工作区 fs，策略、出网白名单、空闲回收；高危命令前端审批  
- **运维**：HolmesGPT HTTP 转发问诊；ttyd 交互终端（可选）  
- **记忆层**：Memdir → 相关性筛选 → Session → Compact / Solip  
- 生产 Docker Compose 部署（Nginx + API + Redis + MySQL）  

---

## 架构（SOLID 分层）

```text
前端门户 / 对话三栏 / 测试工作台 / 运维台 / Electron
        │
        ▼
api/（FastAPI：鉴权、SSE、QA、sandbox、ops、健康检查）
        │
        ▼
orchestration/（ChatOrchestrator：Cursor 路由 → mode Capability）
        │
        ▼
application/（use_cases、qa、sandbox、ops、MCP、Tools、Skills）
        │
        ▼
domain/（RequestContext、RunResult、Ports）
        │
        ▼
infrastructure/（LLM、embeddings、db、sandbox、qa filesystem、releases）
agents/ · rag/ · memory/ · intent/ · billing/
```

核心门面：`application/services/agent_application.py`（依赖组装 + 兼容旧 `ask_*`）。  
HTTP 对话统一走 `app.orchestrator.handle` / `stream`。  
北京时间工具：`shared/timeutil.py`、前端 `frontend/src/utils/beijingTime.ts`。

请求主路径（摘要）：

```text
浏览器 / Electron
  → 中间件（就绪门闩 · 安全头 · CORS）
  → JWT（若开启）
  → api/routes/*
  → ChatOrchestrator / QA / Sandbox / Ops 服务
  → LLM · 向量库 · Redis/SQLite/MySQL · Memdir
```

---

## 目录结构（节选）

```text
api/                   FastAPI（chat / sessions / knowledge / qa / sandbox / ops）
  health_*.py          存活 / 就绪探针与状态机
application/           用例、qa、sandbox、ops、MCP、Tools、Skills
orchestration/         ChatOrchestrator + Capability
domain/                领域模型与 Port
agents/                ReAct / ToolCalling / 多 Agent 图
rag/                   向量、BM25、混合检索、图谱、结构化咨询
memory/                Memdir / Solip / Compact / SessionStore
intent/                意图规划与守卫
infrastructure/        LLM、DB、sandbox 运行时、QA 文件系统
frontend/src/
  portal/              领域门户 domains.ts
  components/qa/       测试工作台
  components/ops/      运维工作台
  components/sandbox/  高危命令审批
electron/              桌面壳
deploy/                Nginx、systemd、更新脚本
docker/sandbox/        沙箱镜像
tests/                 pytest（含 power_test DeepEval）
USAGE.md               ★ 使用手册（根目录）
```

更细的操作步骤见 **[USAGE.md](USAGE.md)**；云部署见 [deploy/README.md](deploy/README.md)。

---

## 环境要求

- Python 3.11+（推荐 3.12/3.13）
- Node.js 18+（前端 / Electron）
- 可选：Redis、MySQL 8（生产 Compose 自带）
- 可选：Docker（平台沙箱 `SANDBOX_ENABLED=true`）
- 可选：npx（Playwright MCP / E2E / QA UI Agent）
- 可选：ttyd / Holmes 服务（运维台）

---

## 快速开始（本地）

> 完整步骤、各工作台用法与排错 → **[USAGE.md](USAGE.md)**

### 1. 后端

```bash
cd LangChain_Demo
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # 或 cp .env.example .env
```

编辑 `.env`，至少配置：

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
```

知识库 / 嵌入（RAG 需要）：

```env
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
```

启动 API（常用本机端口 **8020**）：

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

- 存活：`http://127.0.0.1:8020/health/live`  
- 就绪：`http://127.0.0.1:8020/health/ready`  
- OpenAPI（非生产且开启时）：`http://127.0.0.1:8020/docs`

### 2. 前端

```bash
cd frontend
npm install
# 可选：frontend/.env 中 VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。登录后进入门户；对话 `#/chat`，测试 `#/qa`，运维 `#/ops`。

### 3. Electron 桌面（可选）

```bash
cd frontend
npm run dev:desktop              # 可能自启后端
npm run dev:desktop:no-api       # 后端已手动启动时用
npm run dist                     # 打 Windows 安装包
```

### 4. CLI

```bash
python main.py
```

---

## 对话 API 示例

```bash
curl -s http://127.0.0.1:8020/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"你好\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

开启鉴权后需带 `Authorization: Bearer <token>`（先调登录接口）。  
流式：`POST /api/chat/stream`（SSE）。

支持的 `mode`：`chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`。

| 前缀 | 说明 |
|------|------|
| `/api/qa/*` | 测试工作台 |
| `/api/sandbox/*` | 沙箱（需启用） |
| `/api/ops/*` | 运维 Holmes |
| `/api/ops/terminal/*` | ttyd 终端 |
| `/api/knowledge/*` | 知识库 |
| `/api/sessions/*` | 会话与记忆 |
| `/api/billing/*` | 用量 |

更多 curl 与操作流见 [USAGE.md §10](USAGE.md#10-http-api-速查)。

---

## 配置要点

| 变量 | 含义 |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | 默认聊天模型（OpenAI 兼容） |
| `CURSOR_API_KEY` | 有密钥时，agent / 改代码类 chat 可走 Cursor |
| `MEMORY_BACKEND` | `sqlite`（本地）或 `redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | 鉴权开关；`sqlite` 或 `mysql` |
| `MCP_SERVERS_JSON` | 通用 MCP 服务器 JSON；空则不拉外部 MCP |
| `TAVILY_API_KEY` | `web_search` 工具 |
| `SANDBOX_ENABLED` 等 | 平台沙箱 |
| `HOLMES_*` / `OPS_TTYD_*` | 运维问诊与交互终端 |
| `MEMORY_SOLIP_*` / `MEMDIR_PATH` | 记忆与 Solip |

完整模板：`.env.example`、生产：`.env.production.example`。

前端模型设置保存在本机浏览器；Key 留空时后端用服务端 `.env` 兜底。切换厂商时请同时改 **API Key + API Base + Model Name**。

---

## 测试

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

分层约定：`domain/`、`api/` 不得直接 `import langchain`（由测试闸门检查）。

建议手工冒烟：门户 → 对话 / 测试台 / 运维 → 各 mode 发一轮 → QA 建项目跑用例 →（可选）沙箱审批。

DeepEval 评测（可选）：`tests/power_test/`。

---

## 生产部署（摘要）

推荐 Docker Compose（含 Redis、MySQL、API、Nginx）：

```bash
cp .env.production.example .env   # 填写密钥与管理员密码
docker compose up -d --build
```

- 安全组只开 80/443，不要暴露 8020 / 6379 / 3306  
- 生产：`AUTH_ENABLED=true`、`STRICT_PRODUCTION=true`、`OPENAPI_ENABLED=false`  
- 详情与 GitHub Actions：[deploy/README.md](deploy/README.md)

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 本文件：产品介绍与快速开始 |
| [USAGE.md](USAGE.md) | **使用手册**（本地启动、各台操作、API、排错） |
| [deploy/README.md](deploy/README.md) | 云上 Compose / Nginx / 自动部署 |
| [README_en.md](README_en.md) 等 | 多语言简介 |

---

## 技术栈

- **后端**：FastAPI、LangChain、LangGraph、Chroma、BM25、NetworkX、Redis/SQLite/MySQL、Docker 沙箱  
- **前端**：React 18、Vite、TypeScript、Ant Design、Electron（可选）  
- **工具**：Tavily 搜索、MCP（含 Playwright）、Cursor SDK、HolmesGPT（可选）、ttyd（可选）

---

## 多语言文档

| 语言 | 文件 |
|------|------|
| 中文（主文档） | [README.md](README.md) |
| 使用手册（中文） | [USAGE.md](USAGE.md) |
| English | [README_en.md](README_en.md) |
| 日本語 | [README_ja.md](README_ja.md) |
| 한국어 | [docs/i18n/README_ko.md](docs/i18n/README_ko.md) |
| Español | [docs/i18n/README_es.md](docs/i18n/README_es.md) |

中文 README + USAGE 为主维护版本；其它语言 README 与之对齐（USAGE 目前以中文为准）。

---

## License

[MIT](LICENSE)
