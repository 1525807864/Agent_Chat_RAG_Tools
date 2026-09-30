"""知识库构建用例（支持进度回调）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from shared.errors import AppError, ErrorCode
from shared.path_security import PathSecurityError, resolve_safe_path

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication

# 进度回调：(percent: int, message: str) -> None
ProgressCb = Callable[[int, str], None]


class KnowledgeBuildUseCase:
    """租户文档入库、列表。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    def build(
        self,
        doc_dir: str,
        tenant_id: str = "default",
        *,
        on_progress: Optional[ProgressCb] = None,
    ) -> int:
        """从本地目录构建租户向量库；可选图谱抽取。

        进度约定（给异步 Job / 前端轮询用）：
          读文件 20 → 向量 50 → BM25 60 → 因子 80 → 图谱 95 → 100
        """
        app = self._app

        def _p(pct: int, msg: str) -> None:
            # 回调失败绝不能拖垮建库
            if on_progress is None:
                return
            try:
                on_progress(int(pct), str(msg))
            except Exception:  # noqa: BLE001
                pass

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
        _p(10, "准备读取文档")

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

        _p(20, f"已读取文档块 {len(docs)}")

        if not docs:
            app.logger.warning("未找到任何文档")
            _p(100, "目录为空，跳过")
            return 0

        _p(30, "开始写入向量库（Embedding）")
        count = store.add_documents(docs)
        _p(50, f"向量入库完成 chunks={count}")
        app.logger.info("知识库构建完成, tenant=%s chunks=%s", tenant_id, count)

        from application.tenancy import tenant_bm25_path
        from rag.sparse_bm25 import BM25SparseIndex

        _p(55, "构建 BM25")
        bm25 = BM25SparseIndex()
        bm25.build(docs)
        bm25_path = tenant_bm25_path(app.project_root, tenant_id)
        try:
            bm25.save(bm25_path)
            app.logger.info("BM25 索引已保存: %s (n=%s)", bm25_path, bm25.size)
        except Exception as e:
            app.logger.warning("BM25 保存失败: %s", e)
        _p(60, "BM25 完成")

        from application.tenancy import tenant_factor_records_path
        from rag.structured.extract import extract_factors
        from rag.structured.records import save_record

        _p(65, "抽取结构化因子")
        grouped: dict[str, list[str]] = {}
        suffix_of: dict[str, str] = {}
        for doc in docs:
            src = str((doc.metadata or {}).get("source") or "")
            grouped.setdefault(src, []).append(doc.page_content or "")
            suffix_of[src] = Path(src).suffix.lower()
        records = []
        sources = list(grouped.items())
        for i, (src, parts) in enumerate(sources):
            preview = "\n".join(parts)[:6000]
            factors = extract_factors(app.llm, preview, suffix_of.get(src, ""))
            records.append(
                {"source": src, "suffix": suffix_of.get(src, ""), "factors": factors}
            )
            # 因子阶段 65→80
            if sources:
                _p(65 + int(15 * (i + 1) / len(sources)), f"因子 {i + 1}/{len(sources)}")
        try:
            save_record(
                tenant_factor_records_path(app.project_root, tenant_id),
                records,
            )
            app.logger.info("因子记录已保存: %s 个源文件", len(records))
        except Exception as e:
            app.logger.warning("因子记录保存失败: %s", e)
        _p(80, "因子抽取完成")

        # ----- 图谱：可关 / 可限量 -----
        do_graph = bool(getattr(app.settings, "graph_extract_on_build", True))
        max_docs = int(getattr(app.settings, "graph_extract_max_docs", 0) or 0)
        if not do_graph:
            app.logger.info("已跳过图谱 LLM 抽取（GRAPH_EXTRACT_ON_BUILD=false）")
            _p(95, "跳过图谱抽取")
        else:
            max_chars = app.settings.graph_extract_max_chars
            targets = docs if max_docs <= 0 else docs[:max_docs]
            app.logger.info(
                "图谱抽取: %s/%s chunks", len(targets), len(docs)
            )
            for i, doc in enumerate(targets):
                graph.extract_triples_with_llm(
                    doc.page_content[:max_chars],
                    app.llm,
                    persist=False,
                )
                if targets:
                    _p(
                        80 + int(15 * (i + 1) / len(targets)),
                        f"图谱 {i + 1}/{len(targets)}",
                    )
            try:
                graph.save()
            except Exception as e:
                app.logger.warning("图谱落盘失败: %s", e)
            _p(95, "图谱抽取完成")

        _p(100, "构建完成")
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