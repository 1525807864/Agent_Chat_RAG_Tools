<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**マルチモード AI Agent プラットフォーム · 対話 · RAG · テスト作業台 · サンドボックス**

[機能概要](#機能概要) · [クイックスタート](#クイックスタートローカル) · [デプロイ](deploy/README.md) · [License](LICENSE)

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

LangChain / LangGraph ベースのマルチモード AI Agent プラットフォームです。通常対話、ハイブリッド RAG、構造化コンサル、GraphRAG、ReAct 単体 Agent（MCP 含む）、マルチエージェント連携に対応。FastAPI、Vite/React フロント（AgentHub 風ドメインポータル）、自動テスト作業台、任意の Electron デスクトップを提供します。

デフォルト LLM は DeepSeek / OpenAI / 智譜などのプロトコル互換。任意で Cursor Agent SDK によるコード変更リクエストも可能。時刻は **Asia/Shanghai（北京時間）** で保存・表示します。

---

## 製品入口

ログイン後の既定画面は **作業台ポータル**（hash `#/`）です：

| 領域 | 状態 | 説明 |
|------|------|------|
| 対話プラットフォーム | 公開中 | `#/chat` — マルチモデル / RAG / Agent |
| 自動テストプラットフォーム | 公開中 | `#/qa` — ケース / 実行 / レポート / UI Agent |
| コードレビュー・運用・データ・KB 独立台など | プレースホルダ | カードは「まもなく公開」。垂直 Agent を後から追加可能 |

トップバーの「作業台ホーム」でポータルへ戻れます。対話とテスト台は **インク色 + シャンパンゴールド** で統一しています。

---

## 機能概要

### 対話モード

| モード | 説明 |
|------|------|
| `chat` | セッション記憶（Memory / Solip）+ Skills（`/skill`）+ SSE 真ストリーム |
| `rag` | 密ベクトル + BM25 + RRF ハイブリッド検索、軽量クエリルーティング |
| `consult` | 因子補完の追問後にハイブリッド検索 |
| `graph-rag` | ベクトル検索 + 知識グラフ強化 |
| `agent` | ReAct ツールループ；ワークスペース R/W；汎用 MCP；任意の能動ツール発見；E2E Playwright |
| `multi` | sequential / debate / router マルチエージェント |

### プラットフォーム能力

- **JWT ログインとテナント**、ナレッジベースアップロード/構築、課金台帳、HTTP レート制限とコンテンツフィルタ  
- **自動テスト作業台**：プロジェクト、ケース、実行、レポート出力、メンバー権限、プロジェクト KB；UI Agent（Playwright）  
- **プラットフォームサンドボックス**（任意 Docker）：統一実行面（shell / pwsh / ワークスペース fs）、ポリシー、egress 許可リスト、アイドル回収；高リスクコマンドはフロント承認  
- 本番 Docker Compose デプロイ  

---

## アーキテクチャ（SOLID 層）

```text
ポータル / 対話 3 カラム / テスト作業台 / Electron
        │
        ▼
api/（FastAPI：認証、SSE、QA、sandbox、バリデーション）
        │
        ▼
orchestration/（ChatOrchestrator：Cursor ルーティング → mode Capability）
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

中核ファサード：`application/services/agent_application.py`（DI + 旧 `ask_*` 互換）。  
HTTP 対話は `app.orchestrator.handle` / `stream`。  
北京時間ユーティリティ：`shared/timeutil.py`、フロント `frontend/src/utils/beijingTime.ts`。

---

## ディレクトリ構成（抜粋）

```text
api/                   FastAPI ルート（chat / sessions / knowledge / qa / sandbox）
application/           ユースケース、qa（ui_agent / report_export）、sandbox サービス
orchestration/         ChatOrchestrator + Capability
domain/                ドメインモデルと Port
agents/                ReAct / ToolCalling / マルチ Agent グラフ
rag/                   ベクトル、BM25、ハイブリッド検索、グラフ、コンサル
memory/                セッションストアと MemoryFacade
infrastructure/
  sandbox/             Docker ランタイム、ポリシー、リスク、reaper
  qa/                  テスト基盤ファイルシステム
frontend/src/
  portal/              ドメインポータル設定 domains.ts
  components/HomePortal.tsx
  components/qa/       テスト作業台ページ
  components/sandbox/  高リスク承認パネル
  styles/portal.css    ポータル / インク・金テーマ（index.css も参照）
docker/sandbox/        サンドボックス用 Dockerfile
shared/timeutil.py     北京時間
deploy/                Nginx、systemd、更新スクリプト
tests/                 pytest
docs/assets/           README 用 Logo
docs/i18n/             他言語ドキュメント
```

クラウドデプロイの詳細は [deploy/README.md](deploy/README.md)。

---

## 環境要件

- Python 3.11+（3.12/3.13 推奨）
- Node.js 18+（フロント / Electron）
- 任意：Redis、MySQL 8（本番 Compose に同梱）
- 任意：Docker（プラットフォームサンドボックス `SANDBOX_ENABLED=true`）
- 任意：npx（Playwright MCP / E2E / QA UI Agent）

---

## クイックスタート（ローカル）

### 1. バックエンド

```bash
cd LangChain_Demo
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # または cp .env.example .env
```

`.env` を編集し、最低限以下を設定：

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
```

ナレッジ / 埋め込み（RAG 用）：

```env
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
```

プラットフォームサンドボックス（任意。ローカル Docker とイメージが必要）：

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

サンドボックスイメージ構築例：

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

API 起動（ポート **8020**、Electron 既定と同じ）：

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

ヘルス：`http://127.0.0.1:8020/health`、`/health/ready`  
OpenAPI（非本番かつ有効時）：`http://127.0.0.1:8020/docs`

### 2. フロントエンド

```bash
cd frontend
npm install
# 任意：frontend/.env
# VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

Vite が表示する URL（既定 `http://127.0.0.1:5173`）を開きます。  
ログイン後はポータル；対話 `#/chat`、テスト作業台 `#/qa`。

### 3. Electron デスクトップ（任意）

```bash
cd frontend
npm run dev:desktop
```

API を手動起動済みなら `npm run dev:desktop:no-api`。  
Windows インストーラ：`npm run dist`。

### 4. CLI

```bash
python main.py
```

---

## 対話 API 例

```bash
curl -s http://127.0.0.1:8020/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"こんにちは\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

認証有効時は `Authorization: Bearer <token>` が必要（先にログイン）。  
ストリーム：`POST /api/chat/stream`（SSE）。

対応 `mode`：`chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`。

その他の主なプレフィックス：

| プレフィックス | 説明 |
|------|------|
| `/api/qa/*` | テスト作業台プロジェクト / ケース / 実行 / レポート |
| `/api/sandbox/*` | サンドボックスセッションと実行（要設定） |
| `/api/knowledge/*` | ナレッジドキュメントと構築 |

---

## 設定の要点

| 変数 | 意味 |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | 既定チャットモデル（OpenAI 互換） |
| `CURSOR_API_KEY` | 設定時、agent / コード変更系 chat が Cursor を利用可能 |
| `MEMORY_BACKEND` | `sqlite`（ローカル）または `redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | 認証スイッチ；`sqlite` または `mysql` |
| `MCP_SERVERS_JSON` | 汎用 MCP サーバ JSON 配列；空なら外部 MCP なし |
| `ACTIVE_TOOL_DISCOVERY` | Agent の能動ツール発見（ツールが多いとき） |
| `HYBRID_*` | ハイブリッド検索とルータ |
| `TAVILY_API_KEY` | `web_search` ツール |
| `SANDBOX_ENABLED` など | プラットフォームサンドボックス（`.env.example` 参照） |

テンプレート：`.env.example`、本番：`.env.production.example`。

フロントのモデル設定はブラウザに保存。Key 空ならサーバ `.env` にフォールバック。ベンダー切替時は **API Key + API Base + Model Name** を同時に変更してください。

---

## テスト

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

層の約束：`domain/`、`api/` は直接 `import langchain` しない（テストで検査）。

推奨手動スモーク：ポータル→対話 / テスト台 → 各 mode を 1 回 → QA でプロジェクト作成・実行 →（任意）サンドボックス高リスク承認。

DeepEval 評価（任意、開発依存が必要）：`tests/power_test/`。

---

## 本番デプロイ（要約）

推奨 Docker Compose（Redis、MySQL、API、Nginx）：

```bash
cp .env.production.example .env   # シークレットと管理者パスワードを記入
docker compose up -d --build
```

- セキュリティグループは 80/443 のみ。8020 / 6379 / 3306 を公開しない  
- 本番：`AUTH_ENABLED=true`、`STRICT_PRODUCTION=true`、`OPENAPI_ENABLED=false`  
- 詳細と GitHub Actions 自動デプロイ：[deploy/README.md](deploy/README.md)

---

## 技術スタック

- **バックエンド**：FastAPI、LangChain、LangGraph、Chroma、BM25、NetworkX、Redis/SQLite/MySQL、Docker サンドボックス  
- **フロント**：React 18、Vite、TypeScript、Ant Design、Electron（任意）  
- **ツール**：Tavily 検索、MCP（Playwright E2E / QA UI 含む）、Cursor SDK（任意）

---

## 多言語ドキュメント

| 言語 | ファイル |
|------|------|
| 中文（主ドキュメント） | [README.md](README.md) |
| English | [README_en.md](README_en.md) |
| 日本語 | [README_ja.md](README_ja.md) |
| 한국어 | [docs/i18n/README_ko.md](docs/i18n/README_ko.md) |
| Español | [docs/i18n/README_es.md](docs/i18n/README_es.md) |

各言語は同構成を目指します。保守の基準は中文版です。

---

## License

[MIT](LICENSE)
