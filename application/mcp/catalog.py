"""工具目录：给 discover_tools 做检索。不负责连接 MCP。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from langchain_core.tools import BaseTool

_log = logging.getLogger(__name__)


@dataclass
class ToolHit:
    """一次检索命中。"""

    tool: BaseTool
    score: float
    reason: str


class ToolCatalog:
    """全量工具池的可检索视图。

    策略（由简到繁，和 chapter4 一致思想）：
    1. 关键词重叠（无网络、必可用）
    2. 若能创建 embeddings，再叠加余弦相似度
    """

    def __init__(self, tools: list[BaseTool]) -> None:
        # name -> tool；同名后面覆盖前面
        self._by_name = {t.name: t for t in tools}
        self._tools = list(self._by_name.values())
        self._vectors: list[list[float]] | None = None
        self._embedder = None
        # 避免 embedding 失败后每次 search 都重试建索引
        self._embed_tried = False

    @property
    def all_tools(self) -> list[BaseTool]:
        return list(self._tools)

    def get(self, name: str) -> BaseTool | None:
        return self._by_name.get(name)

    def _doc(self, tool: BaseTool) -> str:
        """把工具名+描述拼成检索文档。"""
        return f"{tool.name}\n{tool.description or ''}"

    def _tokenize(self, text: str) -> set[str]:
        """极简分词：英文单词 + 连续中文/数字。"""
        text = (text or "").lower()
        parts = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text)
        return {p for p in parts if len(p) >= 2}

    def ensure_embeddings(self) -> None:
        """可选：构建向量索引。失败就保持纯关键词，不抛给上层。"""
        if self._embed_tried:
            return
        self._embed_tried = True
        try:
            from infrastructure.embeddings.factory import create_embeddings

            self._embedder = create_embeddings()
            docs = [self._doc(t) for t in self._tools]
            # embed_documents 可能按批；工具数通常 < 200
            self._vectors = self._embedder.embed_documents(docs)
            _log.info("工具目录向量索引完成，n=%s", len(self._vectors))
        except Exception as exc:  # noqa: BLE001
            _log.warning("工具向量索引不可用，仅用关键词: %s", exc)
            self._vectors = None
            self._embedder = None

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        # 手写余弦，避免多引一个依赖
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na <= 0 or nb <= 0:
            return 0.0
        return dot / (na * nb)

    def search(self, need: str, *, top_k: int = 5) -> list[ToolHit]:
        """按自然语言需求检索工具。"""
        need = (need or "").strip()
        if not need:
            return []
        top_k = max(1, min(top_k, 20))
        need_tokens = self._tokenize(need)

        # --- 关键词分 ---
        scored: list[ToolHit] = []
        for tool in self._tools:
            doc = self._doc(tool).lower()
            tokens = self._tokenize(doc)
            overlap = len(need_tokens & tokens)
            # 名称整词命中加权
            name_bonus = 2.0 if tool.name.lower() in need.lower() else 0.0
            score = float(overlap) + name_bonus
            if score > 0:
                scored.append(ToolHit(tool=tool, score=score, reason="keyword"))

        # --- 向量分（有则叠加）---
        self.ensure_embeddings()
        if self._embedder is not None and self._vectors is not None:
            try:
                q = self._embedder.embed_query(need)
                by_name = {h.tool.name: h for h in scored}
                for tool, vec in zip(self._tools, self._vectors):
                    sim = self._cosine(q, vec)
                    # 相似度映射到和关键词相近的量级
                    add = sim * 5.0
                    if tool.name in by_name:
                        by_name[tool.name].score += add
                        by_name[tool.name].reason = "keyword+embed"
                    elif add >= 1.5:
                        by_name[tool.name] = ToolHit(
                            tool=tool, score=add, reason="embed"
                        )
                scored = list(by_name.values())
            except Exception as exc:  # noqa: BLE001
                _log.warning("向量检索失败，回退关键词: %s", exc)

        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]