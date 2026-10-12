<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**マルチモード AI Agent プラットフォーム · 対話 · RAG · テスト作業台 · サンドボックス**

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<br/>

**语言 / Languages**

[中文](README.md) · [English](README_en.md) · [日本語](README_ja.md) · [한국어](docs/i18n/README_ko.md) · [Español](docs/i18n/README_es.md)

</div>

---

Nexora は LangChain / LangGraph ベースのマルチモード AI エージェント基盤です。チャット、ハイブリッド RAG、GraphRAG、ReAct（MCP）、マルチエージェントに対応し、FastAPI と Vite/React のポータル（AgentHub 風）、自動テスト作業台、任意の Electron デスクトップを提供します。

> 詳細な手順・設定は中国語の主ドキュメント **[README.md](README.md)** を参照してください。

---

## 機能概要

| 領域 | 状態 | 説明 |
|------|------|------|
| 対話プラットフォーム | 利用可 | `#/chat` |
| 自動テスト | 利用可 | `#/qa` |
| その他の垂直 Agent | 準備中 | ポータルで「即将开放」 |

対応モード: `chat` · `rag` · `consult` · `graph-rag` · `agent` · `multi`

---

## クイックスタート

```bash
# API
pip install -r requirements.txt
cp .env.example .env   # DEEPSEEK_API_KEY などを設定
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020

# フロント
cd frontend && npm install && npm run dev
```

ブラウザ: `http://127.0.0.1:5173`

---

## その他

- デプロイ: [deploy/README.md](deploy/README.md)  
- License: [MIT](LICENSE)  
- 完全版（中文）: [README.md](README.md) · English: [README_en.md](README_en.md)
