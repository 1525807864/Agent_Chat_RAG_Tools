"""租户路径工具 — 按 tenant_id 隔离向量库 / 图谱 / 文档目录。"""

from __future__ import annotations

from pathlib import Path


def sanitize_tenant_id(tenant_id: str) -> str:
    """只保留安全字符，防止路径穿越。

    返回示例::
        sanitize_tenant_id("acme/../x") -> "acmex"
        sanitize_tenant_id("") -> "default"
    """
    raw = (tenant_id or "").strip()
    safe = "".join(c for c in raw if c.isalnum() or c in "-_")
    return safe or "default"


def tenant_root(project_root: Path, tenant_id: str) -> Path:
    """返回示例: Path('D:/LangChain_Demo/data/tenants/acme')"""
    return Path(project_root) / "data" / "tenants" / sanitize_tenant_id(tenant_id)


def tenant_vector_dir(project_root: Path, tenant_id: str) -> Path:
    """返回示例: .../data/tenants/acme/vector_store"""
    return tenant_root(project_root, tenant_id) / "vector_store"


def tenant_graph_path(project_root: Path, tenant_id: str) -> Path:
    """返回示例: .../data/tenants/acme/knowledge_graph.json"""
    return tenant_root(project_root, tenant_id) / "knowledge_graph.json"


def tenant_docs_dir(project_root: Path, tenant_id: str) -> Path:
    """返回示例: .../data/tenants/acme/docs"""
    return tenant_root(project_root, tenant_id) / "docs"
