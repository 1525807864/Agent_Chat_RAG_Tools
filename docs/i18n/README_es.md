<div align="center">

<img src="../assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**Plataforma de agentes IA multimodal · Chat · RAG · Banco de pruebas · Sandbox**

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)

<br/>

**语言 / Languages**

[中文](../../README.md) · [English](../../README_en.md) · [日本語](../../README_ja.md) · [한국어](README_ko.md) · [Español](README_es.md)

</div>

---

Nexora es una plataforma de agentes IA basada en LangChain / LangGraph: chat, RAG híbrido, GraphRAG, ReAct (MCP), multiagente, con FastAPI, portal React (estilo AgentHub) y banco de pruebas QA.

> Documentación completa (chino): **[README.md](../../README.md)**

---

## Inicio rápido

```bash
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020

cd frontend && npm install && npm run dev
```

- Chat: `#/chat` · QA: `#/qa`  
- Licencia: [MIT](../../LICENSE)
