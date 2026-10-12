<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**Multi-mode AI Agent Platform · Chat · RAG · QA Workbench · Sandbox**

[Features](#features) · [Quick Start](#quick-start) · [Deploy](deploy/README.md) · [License](LICENSE)

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<br/>

**语言 / Languages**

[中文](README.md) · [English](README_en.md) · [日本語](README_ja.md) · [한국어](docs/i18n/README_ko.md) · [Español](docs/i18n/README_es.md)

</div>

---

Nexora is a multi-mode AI agent platform built on LangChain / LangGraph: chat, hybrid RAG, consult, GraphRAG, ReAct agent (MCP), and multi-agent collaboration. It ships with FastAPI, a Vite/React portal (AgentHub-style), an automated QA workbench, and an optional Electron desktop app.

LLMs: DeepSeek / OpenAI / Zhipu (OpenAI-compatible). Optional Cursor Agent SDK. Timestamps use **Asia/Shanghai**.

> Full details (architecture, env vars, sandbox, deploy): see the Chinese main doc **[README.md](README.md)**.

---

## Features

| Area | Status | Notes |
|------|--------|--------|
| Chat workbench | Ready | `#/chat` — multi-model / RAG / Agent |
| Auto QA platform | Ready | `#/qa` — cases / runs / reports / UI Agent |
| Other vertical agents | Coming soon | Portal cards show “即将开放” |

**Modes:** `chat` · `rag` · `consult` · `graph-rag` · `agent` · `multi`

Also: JWT tenancy, knowledge base, billing ledger, rate limits, Docker sandbox (optional), Compose deploy.

---

## Quick start

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # set DEEPSEEK_API_KEY / API_BASE
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

Health: `http://127.0.0.1:8020/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` → portal → Chat `#/chat` or QA `#/qa`.

---

## More

- Deploy: [deploy/README.md](deploy/README.md)  
- License: [MIT](LICENSE)  
- Complete Chinese documentation: [README.md](README.md)
