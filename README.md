# LangChain Demo Agent

基于 LangChain / LangGraph 的多模式 AI Agent 演示项目：普通对话、混合检索 RAG、结构化咨询、GraphRAG、ReAct 单 Agent（含 MCP）、多智能体协作；提供 FastAPI、Vite/React 前端，以及可选 Electron 桌面端。

默认 LLM 兼容 DeepSeek / OpenAI 协议；可选 Cursor Agent SDK 处理改代码类请求。

---

## 功能概览

| 模式 | 说明 |
|------|------|
| `chat` | 会话记忆（Memory / Solip）+ Skills（`/skill`）+ SSE 真流式 |
| `rag` | 稠密向量 + BM25 + RRF 混合检索，轻量查询路由 |
| `consult` | 因子补全追问后再混合检索 |
| `graph-rag` | 向量检索 + 知识图谱增强 |
| `agent` | ReAct 工具环；工作区读写；通用 MCP；可选主动工具发现；E2E Playwright |
| `multi` | sequential / debate / router 多智能体 |

其它能力：JWT 登录与租户、知识库建库、计费账本、HTTP 限流与内容过滤、生产 Docker Compose 部署。

---

## 架构（SOLID 分层）

```text
前端 / Electron / CLI
        │
        ▼
api/（FastAPI，薄适配：鉴权、SSE、参数校验）
        │
        ▼
orchestration/（ChatOrchestrator：Cursor 路由 → mode Capability）
        │
        ▼
application/use_cases/（Chat / Rag / Agent / …）
        │
        ▼
domain/（RequestContext、RunResult、Ports）
        │
        ▼
infrastructure / rag / agents / memory / MCP 适配
```

核心门面：`application/services/agent_application.py`（依赖组装 + 兼容旧 `ask_*`）。  
HTTP 对话统一走 `app.orchestrator.handle` / `stream`，不再在路由里堆 mode 分支。

---

## 目录结构（节选）

```text
api/                 FastAPI 路由、鉴权、schemas
application/         用例、编排依赖、MCP、Tools 网关、Skills 运行时
orchestration/       ChatOrchestrator + Capability
domain/              领域模型与 Port
agents/              ReAct / ToolCalling / 多 Agent 图
rag/                 向量、BM25、混合检索、图谱、结构化咨询
memory/              会话存储与 MemoryFacade
frontend/            Vite + React
electron/            桌面壳
deploy/              Nginx、systemd、更新脚本
tests/               pytest（编排、分层闸、用例 mock 等）
```

更细的云部署说明见 [deploy/README.md](deploy/README.md)。

---

## 环境要求

- Python 3.11+（推荐 3.12/3.13）
- Node.js 18+（前端 / Electron）
- 可选：Redis、MySQL 8（生产 Compose 自带）
- 可选：npx（Playwright MCP / E2E）

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

启动 API（常用本机端口 **8020**，与 Electron 默认一致；文档示例也可用 8000）：

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

健康检查：`http://127.0.0.1:8020/health`  
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

完整模板：`.env.example`、生产：`.env.production.example`。

---

## 测试

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py -q
```

分层约定：`domain/`、`api/` 不得直接 `import langchain`（由测试闸门检查）。

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

- **后端**：FastAPI、LangChain、LangGraph、Chroma、BM25、NetworkX、Redis/SQLite/MySQL  
- **前端**：React 18、Vite、TypeScript、Electron（可选）  
- **工具**：Tavily 搜索、MCP（含 Playwright E2E）、Cursor SDK（可选）

---

## License

[MIT](LICENSE)
