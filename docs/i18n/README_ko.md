<div align="center">

<img src="../assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**멀티 모드 AI Agent 플랫폼 · 대화 · RAG · 테스트 작업대 · 샌드박스**

[기능 개요](#기능-개요) · [빠른 시작](#빠른-시작로컬) · [배포](../../deploy/README.md) · [License](../../LICENSE)

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

LangChain / LangGraph 기반 멀티 모드 AI Agent 플랫폼입니다. 일반 대화, 하이브리드 RAG, 구조화 상담, GraphRAG, ReAct 단일 Agent(MCP 포함), 멀티에이전트 협업을 지원하며 FastAPI, Vite/React 프론트(AgentHub 스타일 도메인 포털), 자동 테스트 작업대, 선택적 Electron 데스크톱을 제공합니다.

기본 LLM은 DeepSeek / OpenAI / 즈푸 등 프로토콜과 호환됩니다. Cursor Agent SDK로 코드 변경 요청을 처리할 수 있습니다. 시간은 **Asia/Shanghai(베이징 시간)** 으로 저장·표시합니다.

---

## 제품 진입점

로그인 후 기본 화면은 **작업대 포털**(hash `#/`)입니다:

| 영역 | 상태 | 설명 |
|------|------|------|
| 대화 플랫폼 | 오픈 | `#/chat` — 멀티모델 / RAG / Agent |
| 자동 테스트 플랫폼 | 오픈 | `#/qa` — 케이스 / 실행 / 리포트 / UI Agent |
| 코드 리뷰, 운영, 데이터, KB 독립대 등 | 플레이스홀더 | 카드에 「곧 공개」. 이후 수직 Agent 접속 가능 |

상단 「작업대 홈」으로 포털로 돌아갈 수 있습니다. 대화와 테스트대는 **잉크색 + 샴페인 골드** 스타일로 통일되어 있습니다.

---

## 기능 개요

### 대화 모드

| 모드 | 설명 |
|------|------|
| `chat` | 세션 메모리(Memory / Solip) + Skills(`/skill`) + SSE 진스트리밍 |
| `rag` | 밀집 벡터 + BM25 + RRF 하이브리드 검색, 경량 쿼리 라우팅 |
| `consult` | 인자 보완 추가 질문 후 하이브리드 검색 |
| `graph-rag` | 벡터 검색 + 지식 그래프 강화 |
| `agent` | ReAct 도구 루프; 워크스페이스 R/W; 일반 MCP; 선택적 능동 도구 발견; E2E Playwright |
| `multi` | sequential / debate / router 멀티에이전트 |

### 플랫폼 역량

- **JWT 로그인·테넌트**, 지식베이스 업로드/구축, 과금 장부, HTTP 제한 및 콘텐츠 필터  
- **자동 테스트 작업대**: 프로젝트, 케이스, 실행, 리포트보내기, 멤버 권한, 프로젝트 KB; UI Agent(Playwright)  
- **플랫폼 샌드박스**(선택 Docker): 통합 실행면(shell / pwsh / 워크스페이스 fs), 정책, egress 허용목록, 유휴 회수; 고위험 명령은 프론트 승인  
- 프로덕션 Docker Compose 배포  

---

## 아키텍처(SOLID 계층)

```text
포털 / 대화 3열 / 테스트 작업대 / Electron
        │
        ▼
api/(FastAPI: 인증, SSE, QA, sandbox, 검증)
        │
        ▼
orchestration/(ChatOrchestrator: Cursor 라우팅 → mode Capability)
        │
        ▼
application/(use_cases, qa, sandbox, MCP, Tools, Skills)
        │
        ▼
domain/(RequestContext, RunResult, Ports)
        │
        ▼
infrastructure/(rag, agents, memory, sandbox, qa filesystem, MCP)
```

핵심 파사드: `application/services/agent_application.py`(DI + 구 `ask_*` 호환).  
HTTP 대화는 `app.orchestrator.handle` / `stream`.  
베이징 시간 유틸: `shared/timeutil.py`, 프론트 `frontend/src/utils/beijingTime.ts`.

---

## 디렉터리 구조(발췌)

```text
api/                   FastAPI 라우트(chat / sessions / knowledge / qa / sandbox)
application/           유스케이스, qa(ui_agent / report_export), sandbox 서비스
orchestration/         ChatOrchestrator + Capability
domain/                도메인 모델과 Port
agents/                ReAct / ToolCalling / 멀티 Agent 그래프
rag/                   벡터, BM25, 하이브리드 검색, 그래프, 상담
memory/                세션 저장소와 MemoryFacade
infrastructure/
  sandbox/             Docker 런타임, 정책, 위험, reaper
  qa/                  테스트 플랫폼 파일시스템
frontend/src/
  portal/              도메인 포털 설정 domains.ts
  components/HomePortal.tsx
  components/qa/       테스트 작업대 페이지
  components/sandbox/  고위험 승인 패널
  styles/portal.css    포털 / 잉크·금 테마(index.css 참고)
docker/sandbox/        샌드박스 Dockerfile
shared/timeutil.py     베이징 시간
deploy/                Nginx, systemd, 업데이트 스크립트
tests/                 pytest
docs/assets/           README Logo
docs/i18n/             기타 언어 문서
```

클라우드 배포 상세: [deploy/README.md](../../deploy/README.md).

---

## 환경 요구

- Python 3.11+(3.12/3.13 권장)
- Node.js 18+(프론트 / Electron)
- 선택: Redis, MySQL 8(프로덕션 Compose 포함)
- 선택: Docker(플랫폼 샌드박스 `SANDBOX_ENABLED=true`)
- 선택: npx(Playwright MCP / E2E / QA UI Agent)

---

## 빠른 시작(로컬)

### 1. 백엔드

```bash
cd LangChain_Demo
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # 또는 cp .env.example .env
```

`.env` 편집, 최소 설정:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
```

지식베이스 / 임베딩(RAG용):

```env
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
```

플랫폼 샌드박스(선택, 로컬 Docker와 이미지 필요):

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

샌드박스 이미지 빌드 예:

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

API 시작(포트 **8020**, Electron 기본과 동일):

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

헬스: `http://127.0.0.1:8020/health`, `/health/ready`  
OpenAPI(비프로덕션·활성화 시): `http://127.0.0.1:8020/docs`

### 2. 프론트엔드

```bash
cd frontend
npm install
# 선택: frontend/.env
# VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

Vite가 안내하는 주소(기본 `http://127.0.0.1:5173`)를 엽니다.  
로그인 후 포털; 대화 `#/chat`, 테스트 작업대 `#/qa`.

### 3. Electron 데스크톱(선택)

```bash
cd frontend
npm run dev:desktop
```

API를 이미 수동 실행 중이면 `npm run dev:desktop:no-api`.  
Windows 설치 패키지: `npm run dist`.

### 4. CLI

```bash
python main.py
```

---

## 대화 API 예시

```bash
curl -s http://127.0.0.1:8020/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"안녕하세요\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

인증 사용 시 `Authorization: Bearer <token>` 필요(먼저 로그인).  
스트리밍: `POST /api/chat/stream`(SSE).

지원 `mode`: `chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`.

기타 주요 접두사:

| 접두사 | 설명 |
|------|------|
| `/api/qa/*` | 테스트 작업대 프로젝트 / 케이스 / 실행 / 리포트 |
| `/api/sandbox/*` | 샌드박스 세션과 실행(설정 필요) |
| `/api/knowledge/*` | 지식 문서와 구축 |

---

## 설정 요점

| 변수 | 의미 |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | 기본 채팅 모델(OpenAI 호환) |
| `CURSOR_API_KEY` | 설정 시 agent / 코드 변경 chat이 Cursor 사용 가능 |
| `MEMORY_BACKEND` | `sqlite`(로컬) 또는 `redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | 인증 스위치; `sqlite` 또는 `mysql` |
| `MCP_SERVERS_JSON` | 일반 MCP 서버 JSON 배열; 비면 외부 MCP 없음 |
| `ACTIVE_TOOL_DISCOVERY` | Agent 능동 도구 발견(도구가 많을 때) |
| `HYBRID_*` | 하이브리드 검색과 라우터 |
| `TAVILY_API_KEY` | `web_search` 도구 |
| `SANDBOX_ENABLED` 등 | 플랫폼 샌드박스(`.env.example` 참고) |

템플릿: `.env.example`, 프로덕션: `.env.production.example`.

프론트 모델 설정은 브라우저에 저장됩니다. Key가 비면 서버 `.env`로 폴백. 공급자 전환 시 **API Key + API Base + Model Name**을 함께 변경하세요.

---

## 테스트

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

계층 규칙: `domain/`, `api/`는 직접 `import langchain` 금지(테스트로 검사).

권장 수동 스모크: 포털 → 대화 / 테스트대 → 각 mode 1회 → QA 프로젝트 생성·실행 →(선택) 샌드박스 고위험 승인.

DeepEval 평가(선택, 개발 의존성 필요): `tests/power_test/`.

---

## 프로덕션 배포(요약)

권장 Docker Compose(Redis, MySQL, API, Nginx):

```bash
cp .env.production.example .env   # 시크릿과 관리자 비밀번호 입력
docker compose up -d --build
```

- 보안 그룹은 80/443만. 8020 / 6379 / 3306 노출 금지  
- 프로덕션: `AUTH_ENABLED=true`, `STRICT_PRODUCTION=true`, `OPENAPI_ENABLED=false`  
- 상세 및 GitHub Actions 자동 배포: [deploy/README.md](../../deploy/README.md)

---

## 기술 스택

- **백엔드**: FastAPI, LangChain, LangGraph, Chroma, BM25, NetworkX, Redis/SQLite/MySQL, Docker 샌드박스  
- **프론트**: React 18, Vite, TypeScript, Ant Design, Electron(선택)  
- **도구**: Tavily 검색, MCP(Playwright E2E / QA UI 포함), Cursor SDK(선택)

---

## 다국어 문서

| 언어 | 파일 |
|------|------|
| 中文(주 문서) | [README.md](../../README.md) |
| English | [README_en.md](../../README_en.md) |
| 日本語 | [README_ja.md](../../README_ja.md) |
| 한국어 | [README_ko.md](README_ko.md) |
| Español | [README_es.md](README_es.md) |

각 언어는 동일한 구성을 목표로 합니다. 유지보수의 기준은 중문판입니다.

---

## License

[MIT](../../LICENSE)
