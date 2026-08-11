"""知识图谱构建、检索与持久化（GraphRAG 基础设施）。

能力
====
1. 三元组增删查与 BFS 邻域检索（深度可配置）
2. LLM 抽取三元组：JSON 清洗 + 失败降级（不中断构建）
3. **JSON 落盘**：进程重启后可 ``load`` 恢复（商业可用性关键）
4. GraphRAGRetriever：向量检索 + 图遍历合并 context

持久化格式
==========
``data/knowledge_graph.json``（可配置）::

    {"nodes": [...], "edges": [...], "version": 1}

依赖方向：被 application 组装；不依赖 FastAPI / CLI。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from domain.knowledge import GraphStats, KnowledgeTriple

logger = logging.getLogger(__name__)


def _strip_json_fence(text: str) -> str:
    """去掉 markdown 代码围栏，尽量得到纯 JSON 文本。"""
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        # 去掉首行 ```json / ``` 与末行 ```
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _extract_json_array(text: str) -> Any:
    """从 LLM 输出中稳健解析 JSON 数组；失败抛 ValueError。"""
    s = _strip_json_fence(text)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 尝试截取第一个 [...] 片段
    match = re.search(r"\[[\s\S]*\]", s)
    if not match:
        raise ValueError("响应中未找到 JSON 数组")
    return json.loads(match.group(0))


class KnowledgeGraph:
    """基于 NetworkX 的轻量知识图谱，支持 JSON 持久化。

    Parameters
    ----------
    persist_path:
        默认落盘路径；为 None 时仅内存，不自动读写磁盘。
    auto_load:
        构造时若文件存在则自动加载。
    """

    def __init__(
        self,
        persist_path: str | Path | None = None,
        *,
        auto_load: bool = True,
    ) -> None:
        self.graph = nx.DiGraph()
        self.persist_path = Path(persist_path) if persist_path else None
        if auto_load and self.persist_path and self.persist_path.exists():
            try:
                self.load(self.persist_path)
                logger.info(
                    "知识图谱已从磁盘恢复: %s (nodes=%s, edges=%s)",
                    self.persist_path,
                    self.graph.number_of_nodes(),
                    self.graph.number_of_edges(),
                )
            except Exception as e:
                logger.warning("知识图谱加载失败，使用空图: %s", e)

    # ----- 写入 -----

    def add_triple(
        self,
        subject: str,
        relation: str,
        obj: str,
        metadata: Optional[dict] = None,
        *,
        persist: bool = False,
    ) -> None:
        """写入一条三元组；可选立即落盘。"""
        subj = subject.strip().lower()
        obj_key = obj.strip().lower()
        rel = relation.strip()
        if not subj or not obj_key or not rel:
            return

        if subj not in self.graph:
            self.graph.add_node(subj, label=subject.strip(), type="entity")
        if obj_key not in self.graph:
            self.graph.add_node(obj_key, label=obj.strip(), type="entity")

        self.graph.add_edge(subj, obj_key, relation=rel, metadata=metadata or {})
        if persist:
            self.save()

    def extract_triples_with_llm(
        self,
        text: str,
        llm,
        *,
        persist: bool = True,
    ) -> list[tuple]:
        """用 LLM 抽取三元组并写入图；解析失败返回 []（降级，不抛）。"""
        prompt = f"""从以下文本中提取 (主语, 关系, 宾语) 三元组, 以 JSON 数组格式返回。

文本: {text[:3000]}

返回格式示例:
[
  {{"subject": "Python", "relation": "是一种", "object": "编程语言"}},
  {{"subject": "Python", "relation": "由...创建", "object": "Guido van Rossum"}}
]

只返回 JSON 数组, 不要其他内容。如果没有关系, 返回空数组 []。
"""
        try:
            from langchain_core.messages import HumanMessage

            response = llm.invoke([HumanMessage(content=prompt)]).content
            triples_data = _extract_json_array(response)
            if not isinstance(triples_data, list):
                logger.warning("三元组抽取结果不是数组，已忽略")
                return []

            triples: list[tuple] = []
            for item in triples_data:
                if not isinstance(item, dict):
                    continue
                subj = item.get("subject") or item.get("s")
                rel = item.get("relation") or item.get("r") or item.get("predicate")
                obj = item.get("object") or item.get("o")
                if not (subj and rel and obj):
                    continue
                triples.append((str(subj), str(rel), str(obj)))
                self.add_triple(str(subj), str(rel), str(obj))

            if persist and triples:
                self.save()
            return triples
        except Exception as e:
            logger.warning("三元组抽取失败（已降级为空）: %s", e)
            return []

    # ----- 检索 -----

    def query_entity(self, entity: str, depth: int = 1) -> dict:
        """BFS 查询实体邻域（出边 + 入边），depth 为最大跳数。"""
        entity_key = entity.strip().lower()
        if entity_key not in self.graph:
            return {"entity": entity, "relations": [], "neighbors": []}

        depth = max(1, int(depth))
        relations: list[dict] = []
        neighbors: set[str] = set()
        visited = {entity_key}
        queue: list[tuple[str, int]] = [(entity_key, 0)]

        while queue:
            current, d = queue.pop(0)
            if d >= depth:
                continue
            for neighbor in self.graph.neighbors(current):
                edge_data = self.graph.get_edge_data(current, neighbor) or {}
                relations.append({
                    "from": self.graph.nodes[current].get("label", current),
                    "relation": edge_data.get("relation", ""),
                    "to": self.graph.nodes[neighbor].get("label", neighbor),
                })
                neighbors.add(neighbor)
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, d + 1))
            for predecessor in self.graph.predecessors(current):
                edge_data = self.graph.get_edge_data(predecessor, current) or {}
                relations.append({
                    "from": self.graph.nodes[predecessor].get("label", predecessor),
                    "relation": edge_data.get("relation", ""),
                    "to": self.graph.nodes[current].get("label", current),
                })
                neighbors.add(predecessor)
                if predecessor not in visited:
                    visited.add(predecessor)
                    queue.append((predecessor, d + 1))

        return {
            "entity": entity,
            "relations": relations,
            "neighbors": [self.graph.nodes[n].get("label", n) for n in neighbors],
        }

    def search_related(
        self,
        keyword: str,
        max_results: int = 10,
        *,
        depth: int = 1,
    ) -> list[dict]:
        """按节点名子串匹配后做邻域查询。"""
        keyword_lower = keyword.strip().lower()
        if not keyword_lower:
            return []
        results: list[dict] = []
        for node in self.graph.nodes:
            if keyword_lower in node:
                results.append(self.query_entity(node, depth=depth))
                if len(results) >= max_results:
                    break
        return results

    def get_graph_stats(self) -> dict:
        """兼容旧 API 的统计 dict。"""
        return self.stats().to_dict()

    def stats(self) -> GraphStats:
        return GraphStats(
            nodes=self.graph.number_of_nodes(),
            edges=self.graph.number_of_edges(),
            density=float(nx.density(self.graph)) if self.graph.number_of_nodes() else 0.0,
            connected_components=(
                nx.number_weakly_connected_components(self.graph)
                if self.graph.number_of_nodes()
                else 0
            ),
            persist_path=str(self.persist_path) if self.persist_path else None,
        )

    def list_triples(self) -> list[KnowledgeTriple]:
        triples: list[KnowledgeTriple] = []
        for u, v, data in self.graph.edges(data=True):
            triples.append(
                KnowledgeTriple(
                    subject=self.graph.nodes[u].get("label", u),
                    relation=data.get("relation", ""),
                    object=self.graph.nodes[v].get("label", v),
                    metadata=data.get("metadata") or {},
                )
            )
        return triples

    # ----- 持久化 -----

    def save(self, filepath: str | Path | None = None) -> None:
        """将图序列化为 JSON（节点 + 边）。优先于 GraphML，便于跨版本与手工检查。"""
        path = Path(filepath) if filepath else self.persist_path
        if path is None:
            raise ValueError("未指定图谱持久化路径")
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 1,
            "nodes": [
                {
                    "id": n,
                    "label": data.get("label", n),
                    "type": data.get("type", "entity"),
                }
                for n, data in self.graph.nodes(data=True)
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "relation": data.get("relation", ""),
                    "metadata": data.get("metadata") or {},
                }
                for u, v, data in self.graph.edges(data=True)
            ],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        self.persist_path = path
        logger.debug("知识图谱已保存: %s", path)

    def load(self, filepath: str | Path | None = None) -> None:
        """从 JSON（或兼容旧 GraphML）加载图谱，覆盖当前内存图。"""
        path = Path(filepath) if filepath else self.persist_path
        if path is None or not path.exists():
            raise FileNotFoundError(f"图谱文件不存在: {path}")

        if path.suffix.lower() in {".graphml", ".xml"}:
            self.graph = nx.read_graphml(path)
            self.persist_path = path
            return

        data = json.loads(path.read_text(encoding="utf-8"))
        g = nx.DiGraph()
        for node in data.get("nodes", []):
            nid = node["id"]
            g.add_node(
                nid,
                label=node.get("label", nid),
                type=node.get("type", "entity"),
            )
        for edge in data.get("edges", []):
            g.add_edge(
                edge["source"],
                edge["target"],
                relation=edge.get("relation", ""),
                metadata=edge.get("metadata") or {},
            )
        self.graph = g
        self.persist_path = path

    def clear(self, *, persist: bool = False) -> None:
        self.graph = nx.DiGraph()
        if persist:
            self.save()


class GraphRAGRetriever:
    """GraphRAG 检索器 — 融合向量检索与图谱邻域。

    Parameters
    ----------
    depth:
        图遍历跳数（Settings.graph_rag_depth）。
    top_k:
        向量检索条数。
    """

    EMPTY_CONTEXT_HINT = (
        "（未检索到相关文档片段，且知识图谱中无匹配实体。"
        "请先构建知识库，或换用更具体的问题。）"
    )

    def __init__(
        self,
        vector_store_manager,
        knowledge_graph: KnowledgeGraph,
        *,
        depth: int = 2,
        top_k: int = 5,
    ) -> None:
        self.vector_store = vector_store_manager
        self.kg = knowledge_graph
        self.depth = max(1, int(depth))
        self.top_k = max(1, int(top_k))

    def retrieve(self, query: str, top_k: int | None = None) -> dict:
        k = top_k or self.top_k
        vector_docs = []
        try:
            vector_docs = self.vector_store.similarity_search(query, k=k)
        except Exception as e:
            logger.warning("向量检索失败，将仅尝试图谱: %s", e)

        keywords = self._extract_keywords(query)
        graph_results: list[dict] = []
        for kw in keywords[:5]:
            graph_results.extend(
                self.kg.search_related(kw, max_results=3, depth=self.depth)
            )

        # 去重：同一 entity 只保留一份
        seen_entities: set[str] = set()
        deduped: list[dict] = []
        for item in graph_results:
            key = str(item.get("entity", "")).lower()
            if key and key not in seen_entities:
                seen_entities.add(key)
                deduped.append(item)
        graph_results = deduped

        context_parts: list[str] = []
        if vector_docs:
            context_parts.append("=== 相关文档片段 ===")
            for i, doc in enumerate(vector_docs, 1):
                source = getattr(doc, "metadata", {}) or {}
                src = source.get("source", "未知来源") if isinstance(source, dict) else "未知来源"
                content = doc.page_content[:500]
                context_parts.append(f"[文档{i} | {src}] {content}")
        else:
            context_parts.append("=== 相关文档片段 ===\n（未找到相关文档）")

        relation_lines: list[str] = []
        for result in graph_results:
            for rel in result.get("relations") or []:
                relation_lines.append(
                    f"({rel['from']}) --[{rel['relation']}]--> ({rel['to']})"
                )

        if relation_lines:
            context_parts.append("\n=== 知识图谱关联 ===")
            # 限制行数，避免 prompt 爆炸
            context_parts.extend(relation_lines[:40])
        else:
            context_parts.append("\n=== 知识图谱关联 ===\n（图谱中无匹配关系）")

        merged = "\n".join(context_parts)
        if not vector_docs and not relation_lines:
            merged = self.EMPTY_CONTEXT_HINT

        return {
            "vector_results": vector_docs,
            "graph_results": graph_results,
            "merged_context": merged,
            "empty": not vector_docs and not relation_lines,
        }

    def _extract_keywords(self, text: str, max_len: int = 8) -> list[str]:
        stopwords = {
            "的", "是", "在", "和", "了", "有", "我", "你", "他", "她", "它",
            "我们", "你们", "他们", "什么", "怎么", "如何", "哪些", "一个",
            "a", "an", "the", "is", "are", "was", "were",
            "in", "on", "at", "to", "for", "of", "and", "what", "how",
        }
        words = re.split(r"[，。！？；、\s,.\!\?;:：]+", text)
        return [w for w in words if w and w.lower() not in stopwords and len(w) > 1][:max_len]
