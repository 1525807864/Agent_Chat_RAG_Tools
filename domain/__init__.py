"""领域层：纯业务概念与端口（不依赖框架、不访问 IO）。

核心概念
========
- Session / ChatMessage：多轮对话
- KnowledgeTriple / GraphStats：知识图谱
- AgentRole：多 Agent 协作角色标识

依赖规则：domain ← application ← interfaces；infrastructure 实现 domain.ports。
"""

from domain.knowledge import GraphStats, KnowledgeTriple
from domain.session import ChatMessage

__all__ = ["ChatMessage", "KnowledgeTriple", "GraphStats"]
