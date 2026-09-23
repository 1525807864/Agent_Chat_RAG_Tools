"""知识库构建用例。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from shared.errors import AppError, ErrorCode
from shared.path_security import PathSecurityError, resolve_safe_path

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class KnowledgeBuildUseCase:
    """租户文档入库、列表。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    def build(self, doc_dir: str, tenant_id: str = "default") -> int:
        """从本地目录构建租户向量库，并抽取三元组写入租户图谱。"""
        app = self._app
        try:
            safe_dir = resolve_safe_path(
                doc_dir,
                allowed_roots=app.settings.allowed_data_roots,
                project_root=app.project_root,
                must_exist=True,
                expect_dir=True,
            )
        except PathSecurityError as e:
            raise AppError(
                ErrorCode.PATH_DENIED,
                "知识库目录不在允许范围内",
                http_status=400,
                internal=str(e),
            ) from e

        store = app._vector_store_for_tenant(tenant_id)
        graph = app._graph_for_tenant(tenant_id)

        app.logger.info("开始构建知识库: tenant=%s dir=%s", tenant_id, safe_dir)
        docs = app.doc_loader.load_directory(safe_dir)
        load_errors = list(getattr(app.doc_loader, "load_errors", []))
        if load_errors:
            detail = "\n".join(load_errors)
            raise AppError(
                ErrorCode.VALIDATION,
                "有文件未能读入，建库已中止：\n" + detail,
                http_status=400,
                internal=detail,
            )

        if not docs:
            app.logger.warning("未找到任何文档")
            return 0

        count = store.add_documents(docs)
        app.logger.info("知识库构建完成, tenant=%s chunks=%s", tenant_id, count)

        from application.tenancy import tenant_bm25_path
        from rag.sparse_bm25 import BM25SparseIndex

        bm25 = BM25SparseIndex()
        bm25.build(docs)
        bm25_path = tenant_bm25_path(app.project_root, tenant_id)
        try:
            bm25.save(bm25_path)
            app.logger.info("BM25 索引已保存: %s (n=%s)", bm25_path, bm25.size)
        except Exception as e:
            app.logger.warning("BM25 保存失败: %s", e)

        from application.tenancy import tenant_factor_records_path
        from rag.structured.extract import extract_factors
        from rag.structured.records import save_record

        grouped: dict[str, list[str]] = {}
        suffix_of: dict[str, str] = {}
        for doc in docs:
            src = str((doc.metadata or {}).get("source") or "")
            grouped.setdefault(src, []).append(doc.page_content or "")
            suffix_of[src] = Path(src).suffix.lower()
        records = []
        for src, parts in grouped.items():
            preview = "\n".join(parts)[:6000]
            factors = extract_factors(app.llm, preview, suffix_of.get(src, ""))
            records.append(
                {"source": src, "suffix": suffix_of.get(src, ""), "factors": factors}
            )
        try:
            save_record(
                tenant_factor_records_path(app.project_root, tenant_id),
                records,
            )
            app.logger.info("因子记录已保存: %s 个源文件", len(records))
        except Exception as e:
            app.logger.warning("因子记录保存失败: %s", e)

        max_chars = app.settings.graph_extract_max_chars
        for doc in docs:
            graph.extract_triples_with_llm(
                doc.page_content[:max_chars],
                app.llm,
                persist=False,
            )
        try:
            graph.save()
        except Exception as e:
            app.logger.warning("图谱落盘失败: %s", e)
        return count

    def list_docs(self, tenant_id: str = "default") -> list[dict]:
        """列出租户 docs 目录下的文件。"""
        from application.tenancy import tenant_docs_dir

        app = self._app
        root = tenant_docs_dir(app.project_root, tenant_id)
        if not root.is_dir():
            return []
        out: list[dict] = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(root)).replace("\\", "/")
                out.append({"name": p.name, "size": p.stat().st_size, "path": rel})
        return out
