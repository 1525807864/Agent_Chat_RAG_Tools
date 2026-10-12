<div align="center">

<img src="../assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**멀티 모드 AI Agent 플랫폼 · 채팅 · RAG · QA 워크벤치 · 샌드박스**

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)

<br/>

**语言 / Languages**

[中文](../../README.md) · [English](../../README_en.md) · [日本語](../../README_ja.md) · [한국어](README_ko.md) · [Español](README_es.md)

</div>

---

Nexora는 LangChain / LangGraph 기반 멀티 모드 AI 에이전트 플랫폼입니다. 채팅, 하이브리드 RAG, GraphRAG, ReAct(MCP), 멀티 에이전트와 FastAPI + React 포털, 자동 QA 워크벤치를 제공합니다.

> 전체 문서(중국어): **[README.md](../../README.md)**

---

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020

cd frontend && npm install && npm run dev
```

- 채팅: `#/chat` · QA: `#/qa`  
- 라이선스: [MIT](../../LICENSE)
