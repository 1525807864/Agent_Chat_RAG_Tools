<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**多模式 AI Agent 平台 · 对话 · RAG · 测试工作台 · 沙箱**

[功能概览](#功能概览) · [快速开始](#快速开始本地) · [部署](deploy/README.md) · [License](LICENSE)

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

基于 LangChain / LangGraph 的多模式 AI Agent 平台：普通对话、混合检索 RAG、结构化咨询、GraphRAG、ReAct 单 Agent（含 MCP）、多智能体协作；提供 FastAPI、Vite/React 前端（AgentHub 风格领域门户）、自动测试工作台，以及可选 Electron 桌面端。

默认 LLM 兼容 DeepSeek / OpenAI / 智谱等协议；可选 Cursor Agent SDK 处理改代码类请求。时间统一按 **Asia/Shanghai（北京时间）** 写入与展示。

---

## 产品入口

登录后默认进入 **工作台门户**（hash `#/`）：

| 领域 | 状态 | 说明 |
|------|------|------|
| 对话平台 | 已上线 | `#/chat`，多模型 / RAG / Agent |
| 自动测试平台 | 已上线 | `#/qa`，用例 / 执行 / 报告 / UI Agent |
| 代码评审、运维、数据、知识库独立台等 | 占位 | 卡片「即将开放」，后续按垂直 Agent 接入 |

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

- **JWT 登录与租户**、知识库上传/建库、计费账本、HTTP 限流与内容过滤  
- **自动测试工作台**：项目、用例、运行、报告导出、成员权限、项目知识库；UI Agent（Playwright）执行  
- **平台沙箱**（可选 Docker）：统一执行面（shell / pwsh / 工作区 fs），策略、出网白名单、空闲回收；高危命令前端审批  
- 生产 Docker Compose 部署  

---

## 架构（SOLID 分层）

```text
前端门户 / 对话三栏 / 测试工作台 / Electron
        │
        ▼
api/（FastAPI：鉴权、SSE、QA、sandbox、参数校验）
        │
        ▼
orchestration/（ChatOrchestrator：Cursor 路由 → mode Capability）
        │
        ▼
application/（use_cases、qa、sandbox、MCP、Tools、Skills）
        │
        ▼
domain/（RequestContext、RunResult、Ports）
        │
        ▼
infrastructure/（rag、agents、memory、sandbox、qa filesystem、MCP）
```

核心门面：`application/services/agent_application.py`（依赖组装 + 兼容旧 `ask_*`）。  
HTTP 对话统一走 `app.orchestrator.handle` / `stream`。  
北京时间工具：`shared/timeutil.py`、前端 `frontend/src/utils/beijingTime.ts`。

---

## 目录结构（节选）

```text
api/                   FastAPI 路由（chat / sessions / knowledge / qa / sandbox）
application/           用例、qa（含 ui_agent / report_export）、sandbox 服务
orchestration/         ChatOrchestrator + Capability
domain/                领域模型与 Port
agents/                ReAct / ToolCalling / 多 Agent 图
rag/                   向量、BM25、混合检索、图谱、结构化咨询
memory/                会话存储与 MemoryFacade
infrastructure/
  sandbox/             Docker 运行时、策略、审批风险、reaper
  qa/                  测试平台文件系统
frontend/src/
  portal/              领域门户配置 domains.ts
  components/HomePortal.tsx
  components/qa/       测试工作台页面
  components/sandbox/  高危命令审批面板
  styles/portal.css    门户 / 全局墨金主题令牌见 index.css
docker/sandbox/        沙箱镜像 Dockerfile
shared/timeutil.py     北京时间
deploy/                Nginx、systemd、更新脚本
tests/                 pytest
docs/assets/           README 展示用 Logo
docs/i18n/             其它语言简短说明
```

更细的云部署说明见 [deploy/README.md](deploy/README.md)。

---

## 环境要求

- Python 3.11+（推荐 3.12/3.13）
- Node.js 18+（前端 / Electron）
- 可选：Redis、MySQL 8（生产 Compose 自带）
- 可选：Docker（平台沙箱 `SANDBOX_ENABLED=true`）
- 可选：npx（Playwright MCP / E2E / QA UI Agent）

---

## 快速开始（本地）

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

平台沙箱（可选，需本机 Docker 与镜像）：

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

构建沙箱镜像示例：

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

启动 API（常用本机端口 **8020**，与 Electron 默认一致）：

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

健康检查：`http://127.0.0.1:8020/health`、`/health/ready`  
OpenAPI（非生产且开启时）：`http://127.0.0.1:8020/docs`

### 2. 前端

```bash
cd frontend
npm install
# 可选：frontend/.env
# VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

浏览器打开 Vite 提示的地址（默认 `http://127.0.0.1:5173`）。  
登录后进入门户；对话 `#/chat`，测试工作台 `#/qa`。

### 3. Electron 桌面（可选）

```bash
cd frontend
npm run dev:desktop
```

若本机 API 已手动启动，可用 `npm run dev:desktop:no-api`。  
打包 Windows 安装包：`npm run dist`。

### 4. CLI

```bash
python main.py
```

---

## 对话 API 示例

```bash
curl -s http://127.0.0.1:8020/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"你好\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

开启鉴权后需带 `Authorization: Bearer <token>`（先调登录接口）。  
流式：`POST /api/chat/stream`（SSE）。

支持的 `mode`：`chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`。

其它主要前缀：

| 前缀 | 说明 |
|------|------|
| `/api/qa/*` | 测试工作台项目 / 用例 / 运行 / 报告 |
| `/api/sandbox/*` | 沙箱会话与执行（需启用配置） |
| `/api/knowledge/*` | 知识库文档与建库 |

---

## 配置要点

| 变量 | 含义 |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | 默认聊天模型（OpenAI 兼容） |
| `CURSOR_API_KEY` | 有密钥时，agent / 改代码类 chat 可走 Cursor |
| `MEMORY_BACKEND` | `sqlite`（本地）或 `redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | 鉴权开关；`sqlite` 或 `mysql` |
| `MCP_SERVERS_JSON` | 通用 MCP 服务器 JSON 数组；空则不拉外部 MCP |
| `ACTIVE_TOOL_DISCOVERY` | Agent 主动发现工具（工具多时再开） |
| `HYBRID_*` | 混合检索与路由器 |
| `TAVILY_API_KEY` | `web_search` 工具 |
| `SANDBOX_ENABLED` 等 | 平台沙箱（见 `.env.example`） |

完整模板：`.env.example`、生产：`.env.production.example`。

前端模型设置保存在本机浏览器；Key 留空时后端用服务端 `.env` 兜底。切换厂商时请同时改 **API Key + API Base + Model Name**。

---

## 测试

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

分层约定：`domain/`、`api/` 不得直接 `import langchain`（由测试闸门检查）。

建议手工冒烟：门户进入对话 / 测试台 → 各 mode 发一轮 → QA 建项目跑用例 →（可选）沙箱高危命令审批。

DeepEval 评测（可选，需另装开发依赖）：见 `tests/power_test/`。

---

## 生产部署（摘要）

推荐 Docker Compose（含 Redis、MySQL、API、Nginx）：

```bash
cp .env.production.example .env   # 填写密钥与管理员密码
docker compose up -d --build
```

- 安全组只开 80/443，不要暴露 8020 / 6379 / 3306  
- 生产：`AUTH_ENABLED=true`、`STRICT_PRODUCTION=true`、`OPENAPI_ENABLED=false`  
- 详情与 GitHub Actions 自动部署：[deploy/README.md](deploy/README.md)

---

## 技术栈

- **后端**：FastAPI、LangChain、LangGraph、Chroma、BM25、NetworkX、Redis/SQLite/MySQL、Docker 沙箱  
- **前端**：React 18、Vite、TypeScript、Ant Design、Electron（可选）  
- **工具**：Tavily 搜索、MCP（含 Playwright E2E / QA UI）、Cursor SDK（可选）

---

## 多语言文档

| 语言 | 文件 |
|------|------|
| 中文（主文档） | [README.md](README.md) |
| English | [README_en.md](README_en.md) |
| 日本語 | [README_ja.md](README_ja.md) |
| 한국어 | [docs/i18n/README_ko.md](docs/i18n/README_ko.md) |
| Español | [docs/i18n/README_es.md](docs/i18n/README_es.md) |

完整细节以中文主文档为准；其它语言为导读与快速开始摘要。

---

## License

[MIT](LICENSE)
