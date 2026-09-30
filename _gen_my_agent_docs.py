# -*- coding: utf-8 -*-
"""Generate deep analysis markdown under Desktop/My_Agent."""
from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(r"d:\LangChain_Demo")
OUT = Path(r"C:\Users\lee\Desktop\My_Agent")
SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".git",
    "frontend",
    "data",
    ".pytest_cache",
    ".deepeval",
    ".claude",
}


def first_line(doc: str | None) -> str:
    if not doc:
        return ""
    line = doc.strip().splitlines()[0].strip()
    return line[:160]


def scan_module(path: Path) -> list[dict]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except Exception:
        return []
    items: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            items.append(
                {
                    "kind": "F",
                    "name": node.name,
                    "line": node.lineno,
                    "args": args,
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "doc": first_line(ast.get_docstring(node)),
                }
            )
        elif isinstance(node, ast.ClassDef):
            items.append(
                {
                    "kind": "C",
                    "name": node.name,
                    "line": node.lineno,
                    "args": [],
                    "async": False,
                    "doc": first_line(ast.get_docstring(node)),
                }
            )
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in sub.args.args]
                    items.append(
                        {
                            "kind": "M",
                            "name": f"{node.name}.{sub.name}",
                            "line": sub.lineno,
                            "args": args,
                            "async": isinstance(sub, ast.AsyncFunctionDef),
                            "doc": first_line(ast.get_docstring(sub)),
                        }
                    )
    return items


def build_catalog() -> dict[str, list[dict]]:
    catalog: dict[str, list[dict]] = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if rel.startswith("tests/") and "power_test" not in rel:
                # keep tests light; still include power_test
                continue
            items = scan_module(p)
            if items:
                catalog[rel] = items
    return catalog


def write(name: str, text: str) -> None:
    path = OUT / name
    path.write_text(text.lstrip("\n"), encoding="utf-8")
    print(f"wrote {name} ({path.stat().st_size} bytes)")


def md_catalog(catalog: dict[str, list[dict]]) -> str:
    lines = [
        "# 09 · 全库函数 / 类方法目录",
        "",
        "> 由 AST 扫描自动生成（跳过 venv/frontend/data）。含模块路径、行号、参数、首行 docstring。",
        "",
        f"**模块数**: {len(catalog)}",
        "",
    ]
    total = 0
    for rel in sorted(catalog):
        lines.append(f"## `{rel}`")
        lines.append("")
        lines.append("| 类型 | 名称 | 行 | 参数 | 说明 |")
        lines.append("|------|------|----|------|------|")
        for it in catalog[rel]:
            total += 1
            kind = {"F": "函数", "C": "类", "M": "方法"}[it["kind"]]
            async_mark = " async" if it["async"] else ""
            args = ", ".join(it["args"][:12])
            if len(it["args"]) > 12:
                args += ", ..."
            doc = (it["doc"] or "").replace("|", "\\|")
            lines.append(
                f"| {kind}{async_mark} | `{it['name']}` | {it['line']} | `{args}` | {doc} |"
            )
        lines.append("")
    lines.insert(5, f"**符号数**: {total}")
    lines.insert(6, "")
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()

    write(
        "README.md",
        """
# LangChain_Demo 深度项目分析（My_Agent）

本目录基于仓库 `D:/LangChain_Demo` **当前代码**重新梳理，比早期 `PROJECT_AUDIT.md` 更细：分层、请求流、数据落库、大量 Mermaid 图、以及**函数级目录**。

## 文档清单

| 文件 | 内容 |
|------|------|
| [01_ARCHITECTURE.md](./01_ARCHITECTURE.md) | 总体架构、分层、目录、部署与配置 |
| [02_REQUEST_FLOWS.md](./02_REQUEST_FLOWS.md) | HTTP/CLI 请求流、mode 路由、Cursor handoff、流式 |
| [03_DOMAIN_APPLICATION.md](./03_DOMAIN_APPLICATION.md) | domain / application / orchestration / use_cases |
| [04_AGENTS_TOOLS.md](./04_AGENTS_TOOLS.md) | ReAct / ToolCalling / Multi / ToolGateway / MCP |
| [05_MEMORY_BILLING.md](./05_MEMORY_BILLING.md) | MemoryFacade、SessionStore、Memdir、计费账本 |
| [06_RAG_KNOWLEDGE.md](./06_RAG_KNOWLEDGE.md) | 向量/BM25/Hybrid/Consult/GraphRAG/建库进度 |
| [07_API_AUTH_FRONTEND.md](./07_API_AUTH_FRONTEND.md) | FastAPI 路由、鉴权、前端 hooks |
| [08_DATA_SQL.md](./08_DATA_SQL.md) | P0/P1/P2 表、Redis/文件落点、归档 |
| [09_FUNCTION_CATALOG.md](./09_FUNCTION_CATALOG.md) | **全库函数/类方法目录**（AST + docstring） |
| [10_MODULE_DETAIL.md](./10_MODULE_DETAIL.md) | 核心模块逐文件职责与调用关系 |
| [PROJECT_AUDIT.md](./PROJECT_AUDIT.md) | 早期审计（保留对照） |

## 一句话定位

多租户 LangChain Agent 演示系统：FastAPI + React，支持 `chat` / `rag` / `consult` / `graph-rag` / `agent` / `multi`；统一编排 `ChatOrchestrator`；记忆（SessionStore + Memdir + Solip）；用量账本（Redis 热路径 + MySQL flush）；知识库异步/同步建库。

## 核心入口

| 入口 | 命令 / 路径 |
|------|-------------|
| HTTP | `uvicorn api.server:app --reload --port 8020` |
| 交互 CLI | `python main.py` |
| Typer CLI | `python -m cli.app_typer ask ...` |
| 前端 | `frontend` Vite `:5173` |

## 规模快照（扫描时）

- Python 业务符号约 650+（含 tests/skills 等）
- 应用层 `application/` 函数最多，其次 `memory/`、`rag/`、`api/`、`agents/`
""",
    )

    write(
        "01_ARCHITECTURE.md",
        r'''
# 01 · 总体架构

## 1.1 系统定位

`LangChain_Demo` 是一套**多租户、多模式**的 Agent / RAG 应用：

- **协议层**：FastAPI（`api/`）+ React（`frontend/`）+ CLI（`interfaces/cli`、`cli/app_typer`）
- **编排层**：`orchestration.ChatOrchestrator`（先 Cursor handoff，再按 `mode` 分发 Capability）
- **应用层**：`AgentApplication` 组装依赖；`UseCaseBundle` 承载业务用例
- **领域层**：`domain.run`（RequestContext / RunResult）、`domain.ports`（端口协议）
- **基础设施**：LLM（DeepSeek）、向量库、MySQL/Redis/SQLite、MCP、归档

## 1.2 分层示意

```mermaid
flowchart TB
  subgraph Clients
    FE[React frontend]
    CLI[CLI / Typer]
    E2E[Playwright E2E]
  end

  subgraph API["api/ FastAPI"]
    Server[server.py lifespan]
    ChatR[routes/chat]
    SessR[routes/sessions]
    KnowR[routes/knowledge]
    BillR[routes/billing]
    Auth[auth JWT / user_store]
  end

  subgraph Orch["orchestration/"]
    Pipe[ChatOrchestrator]
    Caps[capabilities: chat/rag/consult/graph-rag/agent/multi]
  end

  subgraph App["application/"]
    AA[AgentApplication]
    UC[UseCaseBundle]
    TG[ToolGateway]
    MemB[memory_bootstrap]
    Route[routing handoff/policy]
  end

  subgraph Domain["domain/"]
    RC[RequestContext]
    RR[RunResult]
    Ports[SessionStorePort / UsageLedgerPort / KnowledgeGraphPort]
  end

  subgraph Agents["agents/"]
    ReAct[ReActAgent]
    TCA[ToolCallingAgent]
    Graph[multi_agent_graph]
    Reg[tools_registry]
  end

  subgraph MemBill["memory + billing"]
    MF[MemoryFacade]
    SS[SessionStore redis/sqlite/mysql]
    MD[MemdirStore]
    UL[UsageLedger Redis/Memory]
  end

  subgraph RAG["rag/"]
    VS[VectorStoreManager]
    BM25[BM25SparseIndex]
    HY[HybridRetriever]
    KG[KnowledgeGraph]
  end

  FE --> ChatR
  CLI --> AA
  ChatR --> Pipe
  Pipe --> Caps
  Caps --> UC
  UC --> Agents
  UC --> MemBill
  UC --> RAG
  AA --> UC
  AA --> TG
  TG --> Reg
```

## 1.3 依赖组装（AgentApplication）

```mermaid
flowchart LR
  Settings[get_settings] --> AA[AgentApplication.__init__]
  AA --> LLM[DeepSeekChatModel]
  AA --> VS[VectorStoreManager]
  AA --> KG[KnowledgeGraph + GraphRAGRetriever]
  AA --> TR[create_default_registry]
  AA --> TG[ToolGateway + MCP]
  AA --> Ten[TenantResources]
  AA --> Skills[SkillsRuntime]
  AA --> UL[create_usage_ledger]
  AA --> Sec[SecurityPolicy]
  AA --> DL[DocumentLoader]
  AA --> Bundle[UseCaseBundle]
  AA --> Orch[ChatOrchestrator]
  MemBoot[bootstrap_session_memory] -.-> AA
```

关键文件：`application/services/agent_application.py`。

初始化顺序要点：

1. Settings + Logger + project_root
2. LLM / Vector / KnowledgeGraph
3. ToolRegistry → ToolGateway（MCP JSON）
4. TenantResources / Skills / UsageLedger
5. RateLimiter + ContentFilter → SecurityPolicy
6. DocumentLoader
7. UseCaseBundle(self) + ChatOrchestrator(self)
8. 记忆在 lifespan / CLI 启动时通过 `bootstrap_session_memory` 挂到 `app.memory`

## 1.4 目录地图

| 目录 | 职责 |
|------|------|
| `api/` | HTTP 入口、鉴权、限流中间件、OpenAPI |
| `orchestration/` | 统一编排与 Capability 插件 |
| `application/` | 用例、门面、工具网关、路由策略、MCP、Jobs |
| `domain/` | 与框架无关的上下文/结果/端口 |
| `agents/` | ReAct / ToolCalling / 多 Agent 图 / 工具注册表 |
| `memory/` | 会话消息 + Memdir + Compact/Solip/Relevance |
| `billing/` | 用量累加、Redis 账本、MySQL flush |
| `rag/` | 文档加载、向量、BM25、混合检索、Consult、图谱 |
| `infrastructure/` | DeepSeek LLM、DB 访问、归档 |
| `config/` | Settings / `.env` |
| `safety/` | 内容过滤、限流 |
| `sql/` | P0/P1/P2 schema |
| `frontend/` | Vite React UI |
| `tests/` | pytest + DeepEval power_test |

## 1.5 启动与生命周期

```mermaid
sequenceDiagram
  participant U as uvicorn
  participant S as api.server lifespan
  participant Auth as init_user_store
  participant DB as ensure_all_schemas
  participant App as init_agent_app
  participant Mem as bootstrap_session_memory
  participant KB as fail_stale_running_jobs

  U->>S: startup
  S->>Auth: 用户表 SQLite/MySQL
  S->>DB: P0–P2 建表（MySQL 可达时）
  S->>App: AgentApplication 单例
  S->>Mem: 挂载 MemoryFacade
  S->>KB: 清理僵尸 kb_jobs
  Note over S: yield 服务请求
  U->>S: shutdown
  S->>App: shutdown_agent_app
```

## 1.6 配置轴心 `config/settings.py`

| 分组 | 代表字段 | 作用 |
|------|----------|------|
| LLM | `deepseek_api_key`, `model_name` | 对话模型 |
| Embedding | `embedding_api_*`, `embedding_model` | 向量模型 |
| Memory | `memory_backend` = redis\|sqlite\|mysql | 会话权威存储 |
| Auth | `auth_backend`, JWT_* | 登录用户表 |
| MySQL | `mysql_host/user/password/database` | 用户/业务表 |
| Graph | `graph_extract_on_build`, `graph_extract_max_docs` | 建库是否抽图谱 |
| MCP | `mcp_servers_json`, `active_tool_*` | 外部工具 |
| CORS / 安全 | `cors_origins`, `rate_limit_*` | HTTP 安全 |

**注意**：`MYSQL_HOST` 必须是单一主机名（不可写成 `localhost,127.0.0.1`）。

## 1.7 多租户模型

```mermaid
flowchart LR
  JWT[JWT tenant_id] --> Bind[bind_session_id]
  Bind --> SID["session_id = tenant__clientId"]
  SID --> Msg[chat_messages / SessionStore]
  JWT --> Ledger[usage:tenant:{tid}]
  JWT --> Docs[data/tenants/{tid}/docs]
  JWT --> Vec[tenant vector_store]
```

- HTTP：`AuthUser.tenant_id` 注入 `RequestContext.tenant_id`
- Session：`api/auth/session_scope.bind_session_id` 加前缀防串会话
- 资源：`application/tenant_resources.py` / `tenancy` 按租户拆目录

## 1.8 SOLID / 端口现状

已抽 Port：

- `SessionStorePort`
- `UsageLedgerPort`
- `KnowledgeGraphPort`

LLM / 向量暂未 Port 化（单一 DeepSeek + 单一向量实现）。  
Capability 插件便于开闭扩展新 mode。
''',
    )

    write(
        "02_REQUEST_FLOWS.md",
        r'''
# 02 · 请求流与 Mode 路由

## 2.1 HTTP 同步聊天主路径

```mermaid
sequenceDiagram
  participant FE as Frontend
  participant Chat as api/routes/chat
  participant Auth as get_current_user
  participant Orch as ChatOrchestrator
  participant Cap as Capability
  participant UC as UseCase

  FE->>Chat: POST /api/chat (JWT)
  Chat->>Auth: Bearer JWT → AuthUser
  Chat->>Chat: bind_session_id(tenant, session)
  Chat->>Chat: RequestContext
  Chat->>Orch: handle(ctx)
  Orch->>Orch: try_cursor_answer?
  alt Cursor 命中
    Orch-->>Chat: RunResult(provider=cursor)
  else 本地 Capability
    Orch->>Cap: caps[mode].run
    Cap->>UC: execute(...)
    UC-->>Orch: RunResult
  end
  Chat-->>FE: ChatResponse + meta(usage/sources)
```

### 关键函数

| 位置 | 函数 | 作用 |
|------|------|------|
| `api/routes/chat.py` | `_scoped_chat_request` | session 绑租户前缀 |
| | `_to_context` | ChatRequest → RequestContext |
| | `_dispatch` | 调 orchestrator.handle |
| | `_response_meta` | 拼响应 meta（tenant/usage） |
| | `chat` / `chat_stream` | 同步 / SSE |
| `orchestration/pipeline.py` | `handle` | Cursor → capability |
| | `stream` | chat 真流式；其它伪流式 |
| | `_try_cursor` | handoff + persist + 记 requests |
| | `_run_capability` | 按 mode 找插件 |

## 2.2 Mode → Capability → UseCase

```mermaid
flowchart LR
  mode[ctx.mode] --> C1[chat → ChatCapability → ChatUseCase]
  mode --> C2[rag → RagUseCase]
  mode --> C3[consult → ConsultUseCase]
  mode --> C4[graph-rag → GraphRagUseCase]
  mode --> C5[agent → AgentUseCase]
  mode --> C6[multi → MultiAgentUseCase]
```

实现：`orchestration/capabilities.py` → `default_capabilities()`。  
各 Capability 均传入**真实** `ctx.tenant_id`（含 multi）。

## 2.3 Cursor Handoff

```mermaid
flowchart TD
  A[try_cursor_answer] --> B{decide policy}
  B -->|provider!=cursor| Z[None → DeepSeek]
  B -->|cursor| C{导入 Cursor SDK?}
  C -->|失败| Z
  C -->|成功| D[load_agent_id MySQL或文件]
  D --> E[CursorRunner.ask]
  E -->|成功| F[save_agent_id + 返回答案]
  E -->|异常| Z
```

- 策略：`application/routing/policy.py` → `decide`
- 持久化：`infrastructure/db/session_routing_store`（失败回退 JSON agent_store）

## 2.4 Agent 模式（含记忆）

```mermaid
sequenceDiagram
  participant Cap as AgentCapability
  participant UC as AgentUseCase
  participant Mem as MemoryFacade
  participant TG as ToolGateway
  participant RA as ReActAgent

  Cap->>UC: execute(message, session_id, tenant_id, ...)
  UC->>Mem: load_turn_context
  Mem-->>UC: history + system_extra
  UC->>TG: open_act_session
  TG-->>UC: tools(+MCP)
  UC->>RA: run(task, context{history})
  RA-->>UC: result + usage + tool_calls
  UC->>Mem: persist_turn + bg compact
  UC->>UC: safe_record_run 审计(可选)
```

细节：

- `agents/react_agent.think` 注入 history
- `_needs_web_search` / force-search 避免空转直接 Final Answer
- 计费：`billing.turn_helper.safe_record_turn`

## 2.5 Multi 模式

```mermaid
flowchart TB
  M[MultiAgentUseCase._run] --> Reg[注册 researcher/coder/reviewer]
  Reg --> Orch[MultiAgentOrchestrator / LangGraph]
  Orch --> Modes{sequential / debate / router}
  Modes --> Merge[合并各 agent usage]
  Merge --> Bill[safe_record_turn tenant_id]
```

CLI 必须传 `tenant_id`：

- `ask_multi_agent(..., tenant_id=...)`
- Typer `--tenant`
- 交互 CLI `CLI_TENANT_ID`

## 2.6 流式行为

| mode | 行为 |
|------|------|
| chat | `ChatUseCase.astream` 真 token 流 |
| 其它 | orchestrator 先跑完再 yield 整段 delta + final |
| cursor | 整段当 delta |

## 2.7 知识库构建流

### 同步

`POST /api/knowledge/build` → `KnowledgeBuildUseCase.build`（阻塞至完成）。

### 异步

```mermaid
sequenceDiagram
  participant FE as Frontend
  participant API as /build/async
  participant Job as kb_jobs
  participant Build as knowledge.build

  FE->>API: 立即返回 job_id
  API->>Job: enqueue create_task
  loop 轮询
    FE->>API: GET /build/{id}
  end
  Job->>Build: on_progress(pct,msg)
  Build-->>Job: 更新 progress 5→100
```

进度约定：读文件 20 → 向量 50 → BM25 60 → 因子 80 → 图谱 95 → 100。  
`GRAPH_EXTRACT_ON_BUILD=false` 可跳过图谱 LLM。  
启动时 `fail_stale_running_jobs` 清理 reload 僵尸任务。
''',
    )

    write(
        "03_DOMAIN_APPLICATION.md",
        r'''
# 03 · Domain / Application / Orchestration

## 3.1 Domain：`domain/run.py`

| 类型 | 字段要点 | 用途 |
|------|----------|------|
| `RequestContext` | message, mode, session_id, tenant_id, multi_mode, agent_name, api_*, files | 编排入口，无 FastAPI/LC 对象 |
| `RunResult` | answer, meta, traces | 统一结果；`with_meta` 合并 |
| `StreamEvent` | kind=delta\|final, text, answer, meta | 流式事件 |

## 3.2 Domain Ports：`domain/ports.py`

```mermaid
classDiagram
  class SessionStorePort {
    +get_messages(session_id)
    +add_message(session_id, role, content)
    +get_recent_messages(session_id, n)
    +clear_session(session_id)
    +list_sessions()
  }
  class UsageLedgerPort {
    +add(tenant_id, requests, tokens_in, tokens_out)
    +snapshot(tenant_id)
  }
  class KnowledgeGraphPort {
    +add_triple(...)
    +extract_triples_with_llm(...)
    +query_entity(...)
    +search_related(...)
    +save/load(...)
  }
  SessionStorePort <|.. RedisSessionStore
  SessionStorePort <|.. SqliteSessionStore
  SessionStorePort <|.. MysqlSessionStore
  UsageLedgerPort <|.. RedisUsageLedger
  UsageLedgerPort <|.. InMemoryUsageLedger
  KnowledgeGraphPort <|.. KnowledgeGraph
```

## 3.3 Orchestration

### `ChatOrchestrator`（`orchestration/pipeline.py`）

| 方法 | 行为 |
|------|------|
| `handle` | `_try_cursor` → `_run_capability` |
| `stream` | cursor 伪流；chat 真流；其它整段 |
| `_try_cursor` | handoff + session.persist_turn + record_turn(requests=1) |
| `_run_capability` | 查 caps[mode]；未知 mode → ValueError |

### Capabilities（`orchestration/capabilities.py`）

每个 Capability 实现 `async def run(app, ctx) -> RunResult`，内部调用对应 UseCase，并把 usage/sources 塞进 `meta`。

## 3.4 UseCaseBundle

`application/use_cases/bundle.py` 在构造时创建：

| 属性 | 类 | 主责 |
|------|-----|------|
| `chat` | ChatUseCase | 纯对话 + 记忆 + 流式 |
| `rag` | RagUseCase | Hybrid 检索问答 |
| `consult` | ConsultUseCase | 结构化因子咨询 |
| `graph_rag` | GraphRagUseCase | 向量+图谱 |
| `agent` | AgentUseCase | ReAct/ToolCalling + 工具会话 |
| `multi` | MultiAgentUseCase | 多 Agent 协作 |
| `session` | SessionUseCase | 列表/历史/删除/persist |
| `knowledge` | KnowledgeBuildUseCase | 建库 + on_progress |

## 3.5 典型 UseCase 内部骨架

```mermaid
flowchart TD
  A[execute] --> B[security.check]
  B --> C[resolve LLM]
  C --> D[memory.load_turn_context?]
  D --> E[业务：LLM / RAG / Agent]
  E --> F[extract usage]
  F --> G[safe_record_turn]
  G --> H[memory.persist_turn?]
  H --> I[RunResult]
```

## 3.6 Application 其它关键模块

| 模块 | 职责 |
|------|------|
| `services/ask_compat.py` | 旧 `ask_*` CLI 兼容 mixin |
| `tools/gateway.py` | ToolGateway：注册表 + MCP + 主动发现 |
| `memory_bootstrap.py` | 按 settings 创建 SessionStore + MemoryFacade |
| `routing/policy.py` | Cursor vs DeepSeek 决策 |
| `routing/handoff.py` | try_cursor_answer |
| `jobs/kb_jobs.py` | 异步建库任务状态机 |
| `tenant_resources.py` | 租户 docs / 向量路径 |
| `llm_factory.py` | 请求级覆盖 api_key/model |
| `security_policy.py` | 内容过滤 + 限流封装 |
''',
    )

    write(
        "04_AGENTS_TOOLS.md",
        r'''
# 04 · Agents / Tools / Multi

## 4.1 Agent 家族

```mermaid
flowchart TB
  Base[BaseAgent] --> ReAct[ReActAgent]
  Base --> TCA[ToolCallingAgent]
  Multi[MultiAgentOrchestrator] --> Roles[researcher / coder / reviewer]
  Multi --> Graph[LangGraph multi_agent_graph]
  AgentUC[AgentUseCase] --> Pick{agent_type}
  Pick -->|react| ReAct
  Pick -->|tool_calling| TCA
```

## 4.2 ReActAgent（`agents/react_agent.py`）

### 主循环

```mermaid
flowchart TD
  Start[run] --> Think[think: LLM + history]
  Think --> Parse[parse Thought/Action/Action Input]
  Parse --> Need{_needs_web_search 且尚未搜索?}
  Need -->|是| Force[强制 web_search Action]
  Need -->|否| Act{有 Action?}
  Force --> Act
  Act -->|Final Answer| Done[返回]
  Act -->|工具| Exec[registry/gateway 执行]
  Exec --> Obs[Observation 写入]
  Obs --> Think
```

### 关键方法（细节）

| 方法 | 说明 |
|------|------|
| `run` | 多轮 think→act；累计 usage；返回 answer/tool_calls |
| `think` | 拼 system + history + scratchpad；调 LLM |
| `_parse_react` | 解析 Thought/Action/Input/Final |
| `_needs_web_search` | 启发式：时效/事实类问题需要搜索 |
| `_has_web_search` | scratchpad 是否已出现搜索结果 |
| `_force_search_action` | 改写为 web_search，避免空 Final |

历史：`context["history"]` 来自 MemoryFacade，角色兼容 `assistant`/`ai`。

## 4.3 ToolCallingAgent（`agents/tool_calling_agent.py`）

基于 LLM tool-calling / bind_tools：

1. 打开工具会话（ToolGateway）
2. 多轮 tool_calls → 执行 → 回填 ToolMessage
3. 汇总最终自然语言答案 + usage

## 4.4 Multi Agent

| 组件 | 文件 | 说明 |
|------|------|------|
| Orchestrator | `agents/multi_agent.py` | sequential / debate / router |
| Graph | `agents/multi_agent_graph.py` | LangGraph 状态机备选 |
| UseCase | `application/use_cases/multi.py` | 注册角色、合并 usage、计费 |

角色默认：researcher（检索）、coder（实现）、reviewer（审阅）。

## 4.5 ToolRegistry（`agents/tools_registry.py`）

```mermaid
flowchart LR
  Reg[ToolRegistry] --> FS[read_file / list_dir]
  Reg --> Web[web_search]
  Reg --> Calc[calculator]
  Reg --> Py[execute_python 可选]
  Reg --> E2E[e2e_* 可选]
  TG[ToolGateway] --> Reg
  TG --> MCP[MultiServerMCPClient]
  TG --> Active[active tool discovery]
```

`create_default_registry(allowed_roots, project_root, enable_execute_python)` 控制沙箱根与危险工具。

## 4.6 ToolGateway

| 方法 | 作用 |
|------|------|
| `open_act_session` | 合并本地 + MCP 工具，返回可执行 tools |
| `close` / lifespan | 释放 MCP 连接 |
| 主动发现 | `active_tool_*` 配置时按任务检索工具子集 |

AgentUseCase **只依赖 Gateway**，不直接拼 MCP Client。
''',
    )

    write(
        "05_MEMORY_BILLING.md",
        r'''
# 05 · Memory 与 Billing

## 5.1 Memory 分层

```mermaid
flowchart TB
  Facade[MemoryFacade] --> SS[SessionStorePort]
  Facade --> MD[MemdirStore]
  Facade --> Compact[compact / summarize]
  Facade --> Solip[Solip 下一问题]
  Facade --> Rel[relevance 过滤]
  SS --> Redis[(Redis)]
  SS --> SQLite[(chat_history.db)]
  SS --> MySQL[(chat_messages)]
  MD --> Files[data/memdir/sessions/*.json]
```

## 5.2 MemoryFacade 关键 API

| 方法 | 时机 | 作用 |
|------|------|------|
| `load_turn_context` | 请求前 | 取 recent messages + system_extra（memdir/solip） |
| `persist_turn` | 请求后 | 写 user/assistant；触发后台 compact |
| `list_sessions` / `get_history` / `clear` | Session API | CRUD |
| compact 相关 | 后台 | 超长会话摘要压缩 |

启动：`application/memory_bootstrap.bootstrap_session_memory` 按 `MEMORY_BACKEND` 选 store。

## 5.3 SessionStore 实现对照

| 后端 | 文件 | 特点 |
|------|------|------|
| redis | `memory/session_store.py` | 热路径低延迟 |
| sqlite | 同文件 Sqlite 实现 | 单机默认兜底 |
| mysql | `memory/mysql_session_store.py` | 与 P1 `chat_messages` 对齐 |

共同满足 `SessionStorePort`。

## 5.4 Memdir

`memory/memdir/store.py`：按 session 落 JSON（偏好、摘要、工作记忆）。  
与权威消息流分离：消息在 SessionStore，长记忆在 Memdir。

## 5.5 Billing 热路径

```mermaid
sequenceDiagram
  participant UC as UseCase
  participant Ext as billing.extract
  participant Rec as record_turn / safe_record_turn
  participant Led as UsageLedger
  participant Redis as Redis HASH
  participant My as usage_daily MySQL

  UC->>Ext: 从 LLM/Agent 结果抽 tokens
  Ext-->>UC: TurnUsage
  UC->>Rec: tenant_id + TurnUsage
  Rec->>Led: add(requests, in, out)
  Led->>Redis: HINCRBY usage:tenant:{id}
  Note over My: 异步/手动 flush
  Rec-->>UC: usage meta 回写响应
```

### 关键模块

| 文件 | 职责 |
|------|------|
| `billing/usage.py` | TurnUsage 结构 |
| `billing/extract.py` | 从 LC/Agent 结果抽 token |
| `billing/recorder.py` | record_turn |
| `billing/turn_helper.py` | safe_record_turn（吞异常） |
| `billing/redis_ledger.py` | Redis 实现 |
| `billing/factory.py` | redis / memory 选择 |
| `billing/mysql_flush.py` | 刷入 MySQL 日汇总 |

Cursor 路径无官方 token：只记 `requests=1, model=cursor`。

## 5.6 计费与模式覆盖

| mode | 是否记 usage |
|------|----------------|
| chat / rag / consult / graph-rag / agent / multi | 是（抽 token 或估算） |
| cursor handoff | 仅 requests |
| 建库（embedding） | 视实现；主通话账本以对话为主 |
''',
    )

    write(
        "06_RAG_KNOWLEDGE.md",
        r'''
# 06 · RAG / Knowledge / Graph

## 6.1 检索栈

```mermaid
flowchart LR
  Q[Query] --> Emb[Embedding]
  Emb --> VS[VectorStore Chroma]
  Q --> BM25[BM25SparseIndex]
  VS --> HY[HybridRetriever]
  BM25 --> HY
  HY --> LLM[回答生成]
  Q --> KG[KnowledgeGraph]
  VS --> GR[GraphRAGRetriever]
  KG --> GR
  GR --> LLM
```

## 6.2 建库流水线（KnowledgeBuildUseCase）

```mermaid
flowchart TD
  A[load docs] -->|~20%| B[split chunks]
  B -->|~50%| C[embed + vector upsert]
  C -->|~60%| D[rebuild BM25]
  D -->|~80%| E[consult factor extract]
  E -->|~95%| F{graph_extract_on_build?}
  F -->|yes| G[LLM extract triples]
  F -->|no| H[skip]
  G --> I[100% done]
  H --> I
```

`on_progress(pct, msg)` 回调供 `kb_jobs` / 前端进度条。  
异步：`application/jobs/kb_jobs.py` 内存任务表 + asyncio.create_task。

## 6.3 核心类型

| 模块 | 类/函数 | 说明 |
|------|---------|------|
| `rag/document_loader.py` | DocumentLoader | 加载/切分 |
| `rag/vector_store.py` | VectorStoreManager | Chroma 持久化 |
| `rag/bm25_index.py` | BM25SparseIndex | 稀疏检索 |
| `rag/hybrid.py` | HybridRetriever | 融合排序 |
| `rag/rag_chain.py` | 问答链 | prompt + retrieve + LLM |
| `rag/structured/consult.py` | Consult | 因子记录结构化问答 |
| `rag/knowledge_graph.py` | KnowledgeGraph / GraphRAGRetriever | 三元组 + 扩展检索 |

## 6.4 租户隔离路径

```
data/tenants/{tenant_id}/
  docs/
  vector_store/
  bm25_index.json
  factor_records.json
```

全局图谱路径由 settings `knowledge_graph_path` 控制（可按租户扩展）。

## 6.5 API 表面

| 路由 | 行为 |
|------|------|
| `POST /api/knowledge/build` | 同步建库 |
| `POST /api/knowledge/build/async` | 返回 job_id |
| `GET /api/knowledge/build/{id}` | 查进度 |
| `GET /api/knowledge/docs` | 文档列表 |
| `POST /api/knowledge/upload` | 上传 |
| `GET /api/knowledge/graph/stats` | 图谱统计 |
''',
    )

    write(
        "07_API_AUTH_FRONTEND.md",
        r'''
# 07 · API / Auth / Frontend

## 7.1 FastAPI 路由图

```mermaid
flowchart TB
  App[api.server:app] --> AuthR[/api/auth login register]
  App --> Chat[/api/chat /chat/stream]
  App --> Sess[/api/sessions ...]
  App --> Know[/api/knowledge ...]
  App --> Bill[/api/billing usage flush]
  App --> Health[/health]
  App --> MW[SecurityHeaders + RateLimit]
```

## 7.2 鉴权流

```mermaid
sequenceDiagram
  participant C as Client
  participant L as /api/auth/login
  participant US as user_store
  participant J as jwt_auth
  participant D as get_current_user

  C->>L: username/password
  L->>US: authenticate
  US-->>L: StoredUser(tenant_id)
  L->>J: create_access_token
  J-->>C: Bearer JWT
  C->>D: Authorization header
  D->>J: decode → AuthUser
```

关键：

- `api/auth/deps.get_current_user`
- `api/auth/session_scope.bind_session_id` / `public_session_id`
- CORS：`cors_origins`；预检允许 headers `*`
- 开发：`auth_debug` 可发调试 token（受配置约束）

## 7.3 Chat 请求体要点（`api/schemas.py`）

`ChatRequest`：message, mode, session_id, multi_mode, agent_name, files, active_file, model overrides…  
`ChatResponse`：answer + meta（usage, sources, capability, route_reason…）

## 7.4 前端结构（`frontend/src`）

| 文件 | 职责 |
|------|------|
| `App.tsx` | 布局、模式切换、面板 |
| `hooks/useChat.ts` | 发聊天 / 流式 / session |
| `hooks/useTokenPricing.ts` | 用量展示 |
| `api/endpoints.ts` | REST 路径常量 |
| `components/ChatMessages.tsx` | 消息列表 |
| `components/KnowledgePanel.tsx` | 建库（可同步）+ 进度 |
| `components/TokenPriceCalculator.tsx` | 计价 UI |
| `types/api.ts` | TS 类型 |

```mermaid
flowchart LR
  UI[App] --> UC[useChat]
  UC --> EP[endpoints]
  EP --> API[FastAPI]
  UI --> KP[KnowledgePanel]
  KP --> Build[build / build async]
  UI --> Price[TokenPriceCalculator]
```
''',
    )

    write(
        "08_DATA_SQL.md",
        r'''
# 08 · 数据落点（P0 / P1 / P2）

## 8.1 总体存储分层

```mermaid
flowchart TB
  Hot[热路径] --> Redis[(Redis: session + usage)]
  Auth[权威会话] --> Store{MEMORY_BACKEND}
  Store --> Redis
  Store --> SQLite[(data/chat_history.db)]
  Store --> MySQL[(chat_messages)]
  Biz[业务表] --> MySQL
  Files[文件] --> Disk[data/tenants / memdir / vector / graph]
  Archive[归档] --> infrastructure/archive/transcript
```

## 8.2 Schema 文件

| 文件 | 阶段 | 内容概要 |
|------|------|----------|
| `sql/p0_schema.sql` | P0 | 用量日表、基础审计 |
| `sql/p1_schema.sql` | P1 | chat_messages、session 路由等 |
| `sql/p2_schema.sql` | P2 | memory_items、consult_factors、agent_audit 等 |

启动：`infrastructure/db/schema.ensure_all_schemas()`（MySQL 可达时）。

## 8.3 主要 MySQL 表（逻辑）

```mermaid
erDiagram
  USERS ||--o{ CHAT_MESSAGES : owns
  TENANT ||--o{ USAGE_DAILY : aggregates
  SESSION ||--o| SESSION_ROUTING : cursor_agent_id
  SESSION ||--o{ MEMORY_ITEMS : memdir_sync
  TENANT ||--o{ CONSULT_FACTORS : factors
  SESSION ||--o{ AGENT_AUDIT : runs
```

实现访问层：

- `infrastructure/db/session_routing_store.py`
- `infrastructure/db/memory_items_store.py`
- `infrastructure/db/consult_factors_store.py`
- `infrastructure/db/agent_audit.py`
- `api/auth/user_store.py`（users）

## 8.4 Redis Key 约定（示意）

| Key | 用途 |
|-----|------|
| `usage:tenant:{tid}` | HASH：requests / tokens_in / tokens_out |
| session 相关 | 视 SessionStore Redis 实现前缀 |

Flush：`billing/mysql_flush.py` → 日汇总表。

## 8.5 文件落点

| 路径 | 内容 |
|------|------|
| `data/tenants/{tid}/docs` | 上传文档 |
| `data/tenants/{tid}/vector_store` | Chroma |
| `data/tenants/{tid}/bm25_index.json` | BM25 |
| `data/tenants/{tid}/factor_records.json` | Consult 因子（文件备份） |
| `data/memdir/sessions/*.json` | Memdir |
| `data/chat_history.db` | SQLite 会话兜底 |
| knowledge_graph 路径 | NetworkX 图序列化 |

## 8.6 与 OpenClaw / Claude 式分层对照

| 层 | 本项目对应 |
|----|------------|
| 热缓存 | Redis session/usage |
| 权威消息 | SessionStore（可 MySQL） |
| 工作记忆 | Memdir JSON |
| 审计/因子 | MySQL P2 + agent_audit |
| 大对象 | 租户文件 + 向量库 |
''',
    )

    write(
        "10_MODULE_DETAIL.md",
        r'''
# 10 · 核心模块逐文件职责

## 10.1 调用总览（简化）

```mermaid
flowchart TB
  main[main.py / uvicorn] --> server[api.server]
  server --> deps[api.deps.init_agent_app]
  deps --> AA[AgentApplication]
  AA --> Orch[ChatOrchestrator]
  AA --> UC[UseCaseBundle]
  Orch --> Caps[capabilities]
  Caps --> UC
  UC --> Mem[MemoryFacade]
  UC --> Agents[agents.*]
  UC --> RAG[rag.*]
  UC --> Bill[billing.*]
```

## 10.2 api/

| 文件 | 要点 |
|------|------|
| `server.py` | lifespan、挂路由、CORS、中间件 |
| `deps.py` | 全局 AgentApplication 单例 |
| `middleware.py` | SecurityHeaders、ApiRateLimit |
| `exception_handlers.py` | 统一错误体 |
| `schemas.py` | 全部 Pydantic DTO |
| `routes/chat.py` | 同步/流式聊天 |
| `routes/sessions.py` | 会话 CRUD |
| `routes/knowledge.py` | 建库/上传/图谱 |
| `routes/billing.py` | usage snapshot / flush |
| `routes/auth_login.py` | 登录注册 |
| `auth/*` | JWT、密码、user_store、session_scope |

## 10.3 application/use_cases/

| 文件 | execute 要点 |
|------|----------------|
| `chat.py` | 记忆 + LLM；`astream` |
| `rag.py` | Hybrid 检索 + 生成 + sources |
| `consult.py` | 因子库问答 |
| `graph_rag.py` | GraphRAGRetriever |
| `agent.py` | 记忆 + ToolGateway + ReAct/TCA + 审计 |
| `multi.py` | 多角色 + tenant_id 计费 |
| `session.py` | persist/list/history/delete |
| `knowledge.py` | build + on_progress + 可选图谱 |

## 10.4 agents/

| 文件 | 要点 |
|------|------|
| `base.py` | 公共 LLM/日志接口 |
| `react_agent.py` | ReAct 循环 + force-search |
| `tool_calling_agent.py` | 原生 tool calling |
| `multi_agent.py` | 协作编排 |
| `multi_agent_graph.py` | LangGraph |
| `tools_registry.py` | 本地工具沙箱 |
| `tools/*.py` | 具体工具实现 |

## 10.5 memory/

| 文件 | 要点 |
|------|------|
| `facade.py` | 对外唯一门面 |
| `session_store.py` | Redis/SQLite |
| `mysql_session_store.py` | MySQL 适配 |
| `memdir/store.py` | 文件工作记忆 |
| compact/solip/relevance | 压缩与下一问 |

## 10.6 billing/

| 文件 | 要点 |
|------|------|
| `factory.py` | 创建 ledger |
| `redis_ledger.py` | 热账本 |
| `recorder.py` / `turn_helper.py` | 记录入口 |
| `extract.py` | token 抽取 |
| `mysql_flush.py` | 落日表 |

## 10.7 rag/

见 [06_RAG_KNOWLEDGE.md](./06_RAG_KNOWLEDGE.md)。

## 10.8 infrastructure/

| 文件 | 要点 |
|------|------|
| `llm/deepseek.py` | Chat 模型封装 |
| `db/schema.py` | ensure_all_schemas |
| `db/*_store.py` | P1/P2 表访问 |
| `archive/transcript.py` | 会话归档 |

## 10.9 测试

| 路径 | 说明 |
|------|------|
| `tests/power_test/test_deepeval_agent_min.py` | DeepEval + 真实 API 最小用例 |
| 其它 `tests/` | 单元/集成（目录扫描时部分省略以控体积） |
''',
    )

    # Function catalog
    write("09_FUNCTION_CATALOG.md", md_catalog(catalog))

    # Also dump enriched raw for debugging
    raw_lines = []
    for rel in sorted(catalog):
        raw_lines.append(f"## {rel}")
        for it in catalog[rel]:
            raw_lines.append(
                f"  {it['kind']}:{it['name']}({', '.join(it['args'])}) L{it['line']} | {it['doc']}"
            )
    (OUT / "_fn_catalog_enriched.txt").write_text("\n".join(raw_lines), encoding="utf-8")
    print("enriched raw ok, modules=", len(catalog))


if __name__ == "__main__":
    main()
