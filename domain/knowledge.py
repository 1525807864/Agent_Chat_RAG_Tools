"""知识图谱相关领域模型（值对象）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class KnowledgeTriple:
    """知识三元组：(主语, 关系, 宾语)。"""

    subject: str
    relation: str
    object: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "KnowledgeTriple":
        return KnowledgeTriple(
            subject=self.subject.strip(),
            relation=self.relation.strip(),
            object=self.object.strip(),
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class GraphStats:
    """图谱规模统计，供管理接口与健康展示。"""

    nodes: int
    edges: int
    density: float = 0.0
    connected_components: int = 0
    persist_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "density": self.density,
            "connected_components": self.connected_components,
            "persist_path": self.persist_path,
        }


@dataclass
class GraphRetrieveHit:
    """单次图谱检索命中的实体邻域。"""

    entity: str
    relations: list[dict[str, str]]
    neighbors: list[str]
