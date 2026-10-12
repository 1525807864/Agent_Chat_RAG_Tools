<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**Multi-mode AI Agent Platform · Chat · RAG · QA Workbench · Sandbox**

[Features](#features) · [Quick Start](#quick-start-local) · [Deploy](deploy/README.md) · [License](LICENSE)

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

A multi-mode AI agent platform built on LangChain / LangGraph: normal chat, hybrid RAG, structured consult, GraphRAG, ReAct single agent (with MCP), and multi-agent collaboration. It provides FastAPI, a Vite/React frontend (AgentHub-style domain portal), an automated testing workbench, and an optional Electron desktop client.

Default LLMs are compatible with DeepSeek / OpenAI / Zhipu protocols; an optional Cursor Agent SDK can handle code-change requests. Time is stored and displayed in **Asia/Shanghai (Beijing time)**.

---

## Product entry

After login, the default page is the **workbench portal** (hash `#/`):

| Domain | Status | Description |
|------|------|------|
| Chat platform | Live | `#/chat` — multi-model / RAG / Agent |
| Auto testing platform | Live | `#/qa` — cases / runs / reports / UI Agent |
| Code review, ops, data, standalone KB, etc. | Placeholder | Cards show “Coming soon”; vertical agents can be plugged in later |

The top bar can return to the portal via **Workbench Home**. Chat and QA share an **ink + champagne gold** visual style.

---

## Features

### Chat modes

| Mode | Description |
|------|------|
| `chat` | Session memory (Memory / Solip) + Skills (`/skill`) + true SSE streaming |
| `rag` | Dense vectors + BM25 + RRF hybrid retrieval, lightweight query routing |
| `consult` | Factor completion follow-ups, then hybrid retrieval |
| `graph-rag` | Vector retrieval + knowledge-graph enhancement |
| `agent` | ReAct tool loop; workspace R/W; generic MCP; optional active tool discovery; E2E Playwright |
| `multi` | sequential / debate / router multi-agent |

### Platform capabilities

- **JWT login & tenancy**, knowledge base upload/build, billing ledger, HTTP rate limiting & content filtering  
- **Auto testing workbench**: projects, cases, runs, report export, member roles, project KB; UI Agent (Playwright)  
- **Platform sandbox** (optional Docker): unified execution plane (shell / pwsh / workspace fs), policy, egress allowlist, idle reaper; high-risk commands need frontend approval  
- Production Docker Compose deployment  

---

## Architecture (SOLID layers)

```text
Portal / Chat 3-pane / QA workbench / Electron
        │
        ▼
api/ (FastAPI: auth, SSE, QA, sandbox, validation)
        │
        ▼
orchestration/ (ChatOrchestrator: Cursor routing → mode Capability)
        │
        ▼
application/ (use_cases, qa, sandbox, MCP, Tools, Skills)
        │
        ▼
domain/ (RequestContext, RunResult, Ports)
        │
        ▼
infrastructure/ (rag, agents, memory, sandbox, qa filesystem, MCP)
```

Core facade: `application/services/agent_application.py` (DI + legacy `ask_*` compat).  
HTTP chat goes through `app.orchestrator.handle` / `stream`.  
Beijing time helpers: `shared/timeutil.py`, frontend `frontend/src/utils/beijingTime.ts`.

---

## Directory layout (excerpt)

```text
api/                   FastAPI routes (chat / sessions / knowledge / qa / sandbox)
application/           use cases, qa (ui_agent / report_export), sandbox service
orchestration/         ChatOrchestrator + Capability
domain/                domain models & ports
agents/                ReAct / ToolCalling / multi-agent graphs
rag/                   vectors, BM25, hybrid retrieval, graph, consult
memory/                session store & MemoryFacade
infrastructure/
  sandbox/             Docker runtime, policy, risk, reaper
  qa/                  QA filesystem
frontend/src/
  portal/              domain portal config domains.ts
  components/HomePortal.tsx
  components/qa/       QA workbench pages
  components/sandbox/  high-risk approval sheet
  styles/portal.css    portal / ink-gold tokens also in index.css
docker/sandbox/        sandbox image Dockerfile
shared/timeutil.py     Beijing time
deploy/                Nginx, systemd, update scripts
tests/                 pytest
docs/assets/           README logo
docs/i18n/             other language docs
```

Cloud deploy details: [deploy/README.md](deploy/README.md).

---

## Requirements

- Python 3.11+ (3.12/3.13 recommended)
- Node.js 18+ (frontend / Electron)
- Optional: Redis, MySQL 8 (included in production Compose)
- Optional: Docker (platform sandbox `SANDBOX_ENABLED=true`)
- Optional: npx (Playwright MCP / E2E / QA UI Agent)

---

## Quick start (local)

### 1. Backend

```bash
cd LangChain_Demo
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # or: cp .env.example .env
```

Edit `.env`, at least:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
```

Knowledge base / embeddings (for RAG):

```env
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
```

Platform sandbox (optional; needs local Docker + image):

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

Build sandbox image example:

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

Start API (port **8020**, same as Electron default):

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

Health: `http://127.0.0.1:8020/health`, `/health/ready`  
OpenAPI (when enabled, non-prod): `http://127.0.0.1:8020/docs`

### 2. Frontend

```bash
cd frontend
npm install
# optional: frontend/.env
# VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

Open the Vite URL (default `http://127.0.0.1:5173`).  
After login: portal; chat `#/chat`; QA `#/qa`.

### 3. Electron desktop (optional)

```bash
cd frontend
npm run dev:desktop
```

If API is already running locally: `npm run dev:desktop:no-api`.  
Windows installer: `npm run dist`.

### 4. CLI

```bash
python main.py
```

---

## Chat API example

```bash
curl -s http://127.0.0.1:8020/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"hello\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

With auth enabled, send `Authorization: Bearer <token>` (login first).  
Streaming: `POST /api/chat/stream` (SSE).

Supported `mode`: `chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`.

Other main prefixes:

| Prefix | Description |
|------|------|
| `/api/qa/*` | QA projects / cases / runs / reports |
| `/api/sandbox/*` | Sandbox sessions & exec (when enabled) |
| `/api/knowledge/*` | Knowledge docs & build |

---

## Configuration highlights

| Variable | Meaning |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | Default chat model (OpenAI-compatible) |
| `CURSOR_API_KEY` | When set, agent / code-change chat may use Cursor |
| `MEMORY_BACKEND` | `sqlite` (local) or `redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | Auth switch; `sqlite` or `mysql` |
| `MCP_SERVERS_JSON` | Generic MCP server JSON array; empty = no external MCP |
| `ACTIVE_TOOL_DISCOVERY` | Agent active tool discovery (enable when many tools) |
| `HYBRID_*` | Hybrid retrieval & router |
| `TAVILY_API_KEY` | `web_search` tool |
| `SANDBOX_ENABLED` etc. | Platform sandbox (see `.env.example`) |

Templates: `.env.example`, production: `.env.production.example`.

Frontend model settings live in the browser; empty Key falls back to server `.env`. When switching providers, change **API Key + API Base + Model Name** together.

---

## Testing

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

Layering rule: `domain/` and `api/` must not `import langchain` directly (enforced by tests).

Suggested manual smoke: portal → chat / QA → one turn per mode → create QA project & run cases → (optional) sandbox risky-command approval.

DeepEval evals (optional, extra dev deps): see `tests/power_test/`.

---

## Production deploy (summary)

Recommended Docker Compose (Redis, MySQL, API, Nginx):

```bash
cp .env.production.example .env   # fill secrets & admin password
docker compose up -d --build
```

- Open only 80/443 in security groups; do not expose 8020 / 6379 / 3306  
- Production: `AUTH_ENABLED=true`, `STRICT_PRODUCTION=true`, `OPENAPI_ENABLED=false`  
- Details & GitHub Actions deploy: [deploy/README.md](deploy/README.md)

---

## Tech stack

- **Backend**: FastAPI, LangChain, LangGraph, Chroma, BM25, NetworkX, Redis/SQLite/MySQL, Docker sandbox  
- **Frontend**: React 18, Vite, TypeScript, Ant Design, Electron (optional)  
- **Tools**: Tavily search, MCP (incl. Playwright E2E / QA UI), Cursor SDK (optional)

---

## Multilingual docs

| Language | File |
|------|------|
| Chinese (canonical) | [README.md](README.md) |
| English | [README_en.md](README_en.md) |
| 日本語 | [README_ja.md](README_ja.md) |
| 한국어 | [docs/i18n/README_ko.md](docs/i18n/README_ko.md) |
| Español | [docs/i18n/README_es.md](docs/i18n/README_es.md) |

All language editions aim to cover the same sections; Chinese remains the primary maintained doc.

---

## License

[MIT](LICENSE)
