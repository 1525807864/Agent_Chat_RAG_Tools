<div align="center">

<img src="../assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**Plataforma de agentes IA multimodal · Chat · RAG · Banco de pruebas · Sandbox**

[Funciones](#funciones) · [Inicio rápido](#inicio-rápido-local) · [Despliegue](../../deploy/README.md) · [License](../../LICENSE)

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/frontend-React%2018-61dafb)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)
[![Release](https://img.shields.io/github/v/release/1525807864/Agent_Chat_RAG_Tools?display_name=tag)](https://github.com/1525807864/Agent_Chat_RAG_Tools/releases)

<br/>

**语言 / Languages**

[中文](../../README.md) · [English](../../README_en.md) · [日本語](../../README_ja.md) · [한국어](README_ko.md) · [Español](README_es.md)

</div>

---

Plataforma de agentes IA multimodal basada en LangChain / LangGraph: chat normal, RAG híbrido, consulta estructurada, GraphRAG, agente ReAct único (con MCP) y colaboración multiagente. Incluye FastAPI, frontend Vite/React (portal de dominios estilo AgentHub), banco de pruebas automatizado y cliente de escritorio Electron opcional.

Los LLM por defecto son compatibles con DeepSeek / OpenAI / Zhipu; opcionalmente Cursor Agent SDK para cambios de código. La hora se guarda y muestra en **Asia/Shanghai (hora de Pekín)**.

---

## Entrada del producto

Tras iniciar sesión, la página por defecto es el **portal del workbench** (hash `#/`):

| Dominio | Estado | Descripción |
|------|------|------|
| Plataforma de chat | En vivo | `#/chat` — multimodelo / RAG / Agent |
| Plataforma de pruebas auto | En vivo | `#/qa` — casos / ejecuciones / informes / UI Agent |
| Revisión de código, ops, datos, KB independiente, etc. | Placeholder | Tarjetas «Próximamente»; agentes verticales más adelante |

La barra superior puede volver al portal con **Inicio del workbench**. Chat y QA comparten estilo **tinta + oro champagne**.

---

## Funciones

### Modos de chat

| Modo | Descripción |
|------|------|
| `chat` | Memoria de sesión (Memory / Solip) + Skills (`/skill`) + SSE real |
| `rag` | Vectores densos + BM25 + RRF híbrido, enrutado ligero de consultas |
| `consult` | Seguimiento por factores y luego recuperación híbrida |
| `graph-rag` | Recuperación vectorial + grafo de conocimiento |
| `agent` | Bucle ReAct; R/W del workspace; MCP genérico; descubrimiento activo opcional; E2E Playwright |
| `multi` | multiagente sequential / debate / router |

### Capacidades de plataforma

- **Login JWT y tenancy**, carga/construcción de base de conocimiento, ledger de facturación, rate limit HTTP y filtro de contenido  
- **Banco de pruebas auto**: proyectos, casos, ejecuciones, exportación de informes, roles, KB del proyecto; UI Agent (Playwright)  
- **Sandbox de plataforma** (Docker opcional): plano de ejecución unificado (shell / pwsh / fs del workspace), política, allowlist de egress, reaper de inactividad; comandos de alto riesgo requieren aprobación en frontend  
- Despliegue productivo con Docker Compose  

---

## Arquitectura (capas SOLID)

```text
Portal / Chat 3 columnas / QA / Electron
        │
        ▼
api/ (FastAPI: auth, SSE, QA, sandbox, validación)
        │
        ▼
orchestration/ (ChatOrchestrator: enrutado Cursor → Capability por mode)
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

Fachada central: `application/services/agent_application.py` (DI + compat `ask_*`).  
El chat HTTP pasa por `app.orchestrator.handle` / `stream`.  
Utilidades de hora de Pekín: `shared/timeutil.py`, frontend `frontend/src/utils/beijingTime.ts`.

---

## Estructura de directorios (extracto)

```text
api/                   Rutas FastAPI (chat / sessions / knowledge / qa / sandbox)
application/           casos de uso, qa (ui_agent / report_export), servicio sandbox
orchestration/         ChatOrchestrator + Capability
domain/                modelos de dominio y Ports
agents/                ReAct / ToolCalling / grafos multiagente
rag/                   vectores, BM25, híbrido, grafo, consult
memory/                almacén de sesión y MemoryFacade
infrastructure/
  sandbox/             runtime Docker, política, riesgo, reaper
  qa/                  filesystem del banco de pruebas
frontend/src/
  portal/              config del portal domains.ts
  components/HomePortal.tsx
  components/qa/       páginas del workbench QA
  components/sandbox/  hoja de aprobación de alto riesgo
  styles/portal.css    portal / tokens tinta-oro (también index.css)
docker/sandbox/        Dockerfile del sandbox
shared/timeutil.py     hora de Pekín
deploy/                Nginx, systemd, scripts de actualización
tests/                 pytest
docs/assets/           Logo del README
docs/i18n/             docs en otros idiomas
```

Despliegue en la nube: [deploy/README.md](../../deploy/README.md).

---

## Requisitos

- Python 3.11+ (recomendado 3.12/3.13)
- Node.js 18+ (frontend / Electron)
- Opcional: Redis, MySQL 8 (incluido en Compose de producción)
- Opcional: Docker (sandbox `SANDBOX_ENABLED=true`)
- Opcional: npx (Playwright MCP / E2E / QA UI Agent)

---

## Inicio rápido (local)

### 1. Backend

```bash
cd LangChain_Demo
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # o: cp .env.example .env
```

Edite `.env`, como mínimo:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
```

Base de conocimiento / embeddings (para RAG):

```env
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
```

Sandbox de plataforma (opcional; requiere Docker e imagen local):

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

Ejemplo de build de imagen sandbox:

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

Arranque de la API (puerto **8020**, igual que Electron):

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

Salud: `http://127.0.0.1:8020/health`, `/health/ready`  
OpenAPI (si está habilitado, no prod): `http://127.0.0.1:8020/docs`

### 2. Frontend

```bash
cd frontend
npm install
# opcional: frontend/.env
# VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

Abra la URL de Vite (por defecto `http://127.0.0.1:5173`).  
Tras login: portal; chat `#/chat`; QA `#/qa`.

### 3. Electron (opcional)

```bash
cd frontend
npm run dev:desktop
```

Si la API ya corre: `npm run dev:desktop:no-api`.  
Instalador Windows: `npm run dist`.

### 4. CLI

```bash
python main.py
```

---

## Ejemplo de API de chat

```bash
curl -s http://127.0.0.1:8020/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"hola\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

Con auth: `Authorization: Bearer <token>` (inicie sesión antes).  
Streaming: `POST /api/chat/stream` (SSE).

`mode` soportados: `chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`.

Otros prefijos principales:

| Prefijo | Descripción |
|------|------|
| `/api/qa/*` | Proyectos / casos / runs / informes QA |
| `/api/sandbox/*` | Sesiones y ejecución sandbox (si está activo) |
| `/api/knowledge/*` | Documentos y build de conocimiento |

---

## Puntos de configuración

| Variable | Significado |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | Modelo de chat por defecto (compatible OpenAI) |
| `CURSOR_API_KEY` | Si se define, agent / chat de código puede usar Cursor |
| `MEMORY_BACKEND` | `sqlite` (local) o `redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | Auth; `sqlite` o `mysql` |
| `MCP_SERVERS_JSON` | Array JSON de servidores MCP; vacío = sin MCP externo |
| `ACTIVE_TOOL_DISCOVERY` | Descubrimiento activo de herramientas del Agent |
| `HYBRID_*` | Recuperación híbrida y router |
| `TAVILY_API_KEY` | Herramienta `web_search` |
| `SANDBOX_ENABLED` etc. | Sandbox de plataforma (ver `.env.example`) |

Plantillas: `.env.example`, producción: `.env.production.example`.

Los ajustes de modelo del frontend viven en el navegador; Key vacío usa `.env` del servidor. Al cambiar de proveedor, cambie **API Key + API Base + Model Name** a la vez.

---

## Pruebas

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

Regla de capas: `domain/` y `api/` no deben `import langchain` directamente (lo comprueban los tests).

Smoke manual sugerido: portal → chat / QA → un turno por mode → crear proyecto QA y ejecutar → (opcional) aprobación sandbox de alto riesgo.

Evals DeepEval (opcional, deps de desarrollo): `tests/power_test/`.

---

## Despliegue en producción (resumen)

Compose recomendado (Redis, MySQL, API, Nginx):

```bash
cp .env.production.example .env   # secretos y contraseña de admin
docker compose up -d --build
```

- Solo abrir 80/443; no exponer 8020 / 6379 / 3306  
- Producción: `AUTH_ENABLED=true`, `STRICT_PRODUCTION=true`, `OPENAPI_ENABLED=false`  
- Detalles y GitHub Actions: [deploy/README.md](../../deploy/README.md)

---

## Stack tecnológico

- **Backend**: FastAPI, LangChain, LangGraph, Chroma, BM25, NetworkX, Redis/SQLite/MySQL, sandbox Docker  
- **Frontend**: React 18, Vite, TypeScript, Ant Design, Electron (opcional)  
- **Herramientas**: búsqueda Tavily, MCP (incl. Playwright E2E / QA UI), Cursor SDK (opcional)

---

## Documentación multilingüe

| Idioma | Archivo |
|------|------|
| Chino (canónico) | [README.md](../../README.md) |
| English | [README_en.md](../../README_en.md) |
| 日本語 | [README_ja.md](../../README_ja.md) |
| 한국어 | [README_ko.md](README_ko.md) |
| Español | [README_es.md](README_es.md) |

Todas las ediciones buscan la misma estructura; el chino es la referencia de mantenimiento.

---

## License

[MIT](../../LICENSE)
