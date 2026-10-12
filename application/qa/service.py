"""用例生成（模板）+ 冒烟执行（HTTP 探活）+ UI 测试 + 助手规则改稿。判定不经过 LLM。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from application.qa.serialize import run_out
from application.qa.ui_agent import iter_agent_ui
from config.settings import get_settings
from domain.qa import (
    KIND_API,
    KIND_BLACKBOX,
    KIND_FUNCTIONAL,
    KIND_PERF,
    KIND_SECURITY,
    QaCase,
    QaMember,
    QaProject,
    QaRun,
)
from e2e.url_guard import E2EUrlError, validate_base_url
from infrastructure.qa.filesystem import QaFileStore, _now, _sid


class QaApplication:
    """租户级门面：路由只调这里。"""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.store = QaFileStore(tenant_id)

    # ---------- 项目 ----------

    def list_projects(self) -> list[QaProject]:
        return self.store.list_projects()

    def create_project(self, name: str, base_url: str, goal: str) -> QaProject:
        url = self._lock_url(base_url)
        return self.store.create_project(name=name, base_url=url, goal=goal)

    def get_project(self, project_id: str) -> QaProject:
        return self.store.get_project(project_id)

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        base_url: str | None = None,
        goal: str | None = None,
    ) -> QaProject:
        """PATCH：name / base_url / goal 任一可选。"""
        proj = self.store.get_project(project_id)
        if name is not None:
            proj.name = name.strip()[:80] or proj.name
        if base_url is not None:
            proj.base_url = self._lock_url(base_url)
        if goal is not None:
            proj.goal = goal.strip()[:2000]
        self.store.save_project(proj)
        return proj

    def delete_project(self, project_id: str) -> None:
        """先确认存在再删，给路由 404。"""
        self.store.get_project(project_id)
        self.store.delete_project(project_id)

    def add_local_source(
        self, project_id: str, filename: str, text: str
    ) -> QaProject:
        """上传文档：第一期只存摘录，不接向量库。"""
        self.store.get_project(project_id)
        lower = (filename or "").lower()
        if lower.endswith(".pdf"):
            kind = "pdf"
        elif lower.endswith(".md"):
            kind = "md"
        elif lower.endswith(".docx"):
            kind = "docx"
        else:
            kind = "text"
        excerpt = (text or "").strip().replace("\r\n", "\n")[:400]
        doc = {
            "id": _sid(),
            "name": (filename or "upload.txt")[:120],
            "kind": kind,
            "excerpt": excerpt or "（空文件或无法提取文本）",
        }
        return self.store.add_source_doc(project_id, doc)

    # ---------- 用例 ----------

    def list_cases(self, project_id: str) -> list[QaCase]:
        self.store.get_project(project_id)
        return self.store.list_cases(project_id)

    def generate_cases(
        self, project_id: str, goal: str | None = None
    ) -> list[QaCase]:
        """按目标生成一棵固定结构的树；code 写成 1 / 1.1… 供前端树展示。"""
        proj = self.store.get_project(project_id)
        text = (goal or proj.goal or proj.name or "被测系统").strip()
        doc_ids = [
            str(d.get("id"))
            for d in (proj.source_docs or [])
            if isinstance(d, dict) and d.get("id")
        ]
        root_id = _sid()
        root = QaCase(
            id=root_id,
            project_id=project_id,
            parent_id=None,
            title=f"需求包：{text[:40]}",
            kind=KIND_FUNCTIONAL,
            requirement=text,
            fused=f"围绕「{text}」覆盖打开站点、接口探活、基础功能与占位非功能项。",
            steps=["导入需求", "确认融合描述", "生成子用例"],
            expected="树完整且每条有期望",
            status="confirmed",
            code="1",
            source_doc_ids=list(doc_ids),
        )
        specs = [
            (
                KIND_BLACKBOX,
                "探索性冒烟",
                "打开 Base URL，页面可访问",
                ["浏览器或 HTTP 打开首页"],
                "HTTP 2xx 且有响应体",
            ),
            (
                KIND_FUNCTIONAL,
                "核心功能",
                f"验证与「{text}」相关的主路径",
                ["按融合描述走主路径", "检查关键文案"],
                "主路径无阻断错误",
            ),
            (
                KIND_API,
                "接口探活",
                "对 origin 做 GET 探活（可后续换成 OpenAPI）",
                ["GET base_url"],
                "状态码 < 500",
            ),
            (
                KIND_PERF,
                "性能占位",
                "第一期不跑 k6，只记录 SLO 待填",
                ["填写 p95 阈值"],
                "人工确认阈值",
            ),
            (
                KIND_SECURITY,
                "安全占位",
                "第一期不扫描，只列检查项",
                ["确认不得测未授权目标"],
                "范围已书面确认",
            ),
        ]
        children: list[QaCase] = []
        for i, (kind, title, req, steps, exp) in enumerate(specs, start=1):
            children.append(
                QaCase(
                    id=_sid(),
                    project_id=project_id,
                    parent_id=root_id,
                    title=title,
                    kind=kind,
                    requirement=req,
                    fused=req,
                    steps=steps,
                    expected=exp,
                    status="draft",
                    code=f"1.{i}",
                    source_doc_ids=list(doc_ids),
                )
            )
        return self.store.add_cases(project_id, [root, *children])

    def confirm_case(
        self, project_id: str, case_id: str, fused: str | None
    ) -> QaCase:
        """中栏点「确认」：融合文案入库并标 confirmed。"""
        fields: dict[str, Any] = {"status": "confirmed"}
        if fused is not None:
            fields["fused"] = fused.strip()[:8000]
        return self.store.patch_case(project_id, case_id, **fields)

    def delete_case(self, project_id: str, case_id: str) -> list[QaCase]:
        self.store.get_project(project_id)
        return self.store.delete_case(project_id, case_id)

    # ---------- 运行 ----------

    def list_runs(self, project_id: str) -> list[QaRun]:
        self.store.get_project(project_id)
        return self.store.list_runs(project_id)

    def run_smoke(
        self, project_id: str, case_ids: list[str] | None = None
    ) -> QaRun:
        """对 base_url 做 GET：2xx/3xx 为 pass，否则 fail。"""
        proj = self.store.get_project(project_id)
        url = self._lock_url(proj.base_url)
        if not url:
            raise ValueError("请先填写并保存被测 Base URL")
        ids = case_ids or [c.id for c in self.store.list_cases(project_id)]
        status_code = 0
        err = ""
        body_len = 0
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url)
            status_code = resp.status_code
            body_len = len(resp.content or b"")
        except Exception as exc:  # noqa: BLE001
            err = str(exc)[:500]
        ok = (not err) and 200 <= status_code < 400
        run = QaRun(
            id=_sid(),
            project_id=project_id,
            case_ids=ids,
            verdict="pass" if ok else "fail",
            summary=(
                f"GET {url} -> {status_code}, bytes={body_len}"
                if not err
                else f"GET {url} 异常: {err}"
            ),
            artifacts={
                "url": url,
                "status_code": status_code,
                "body_len": body_len,
                "error": err,
            },
            created_at=_now(),
        )
        return self.store.add_run(run)

    async def iter_ui_run(
        self,
        project_id: str,
        *,
        name: str,
        base_url: str,
        goal: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        """有头智能 UI 测试：LLM 决定操作，Playwright 判定，最后落一条 QaRun。"""
        proj = self.store.get_project(project_id)
        title = (name or proj.name or "UI 测试").strip()[:80]
        task = (goal or title).strip()[:4000]
        raw_url = (base_url or proj.base_url or "").strip()
        url = self._lock_url(raw_url)
        if not url:
            raise ValueError("请填写被测 URL")

        collected: list[dict[str, Any]] = []
        final: dict[str, Any] | None = None
        async for ev in iter_agent_ui(name=title, url=url, goal=task):
            if ev.get("type") == "done":
                final = ev
                continue  # 落盘后再发给前端
            collected.append(ev)
            yield ev

        if final is None:
            final = {
                "verdict": "error",
                "summary": "未收到结束事件",
                "steps": collected,
                "name": title,
                "url": url,
                "goal": task,
            }

        run = QaRun(
            id=_sid(),
            project_id=project_id,
            case_ids=[],
            verdict=str(final.get("verdict") or "error"),
            summary=str(final.get("summary") or ""),
            artifacts={
                "kind": "ui-agent",
                "name": title,
                "goal": task,
                "url": url,
                "steps": final.get("steps") or collected,
            },
            created_at=_now(),
        )
        saved = self.store.add_run(run)
        yield {
            "type": "done",
            "verdict": saved.verdict,
            "summary": saved.summary,
            "steps": final.get("steps") or collected,
            "name": title,
            "url": url,
            "goal": task,
            "run": run_out(saved),
        }

    def get_run(self, project_id: str, run_id: str) -> QaRun:
        """导出前读取单次运行。"""
        self.store.get_project(project_id)
        return self.store.get_run(project_id, run_id)

    # ---------- 助手（规则改稿，第一期不调 LLM）----------

    def apply_assistant(
        self, project_id: str, case_id: str | None, text: str
    ) -> dict[str, Any]:
        """返回 { reply, cases, selected_id }，cases 为领域对象列表。"""
        self.store.get_project(project_id)
        cases = self.store.list_cases(project_id)
        note = (text or "").strip()[:500]
        if not note:
            raise ValueError("消息不能为空")
        if not case_id:
            return {
                "reply": "请先在左侧选中一条测试内容，再说要改什么。",
                "cases": cases,
                "selected_id": None,
            }
        target = next((c for c in cases if c.id == case_id), None)
        if not target:
            raise FileNotFoundError(case_id)
        target.fused = (target.fused + "\n\n[助手修订] " + note).strip()[:8000]
        target.status = "draft"
        self.store.save_cases(project_id, cases)
        return {
            "reply": f"已把修订记入「{target.title}」的融合需求，请在中栏确认。",
            "cases": cases,
            "selected_id": case_id,
        }

    # ---------- 成员 ----------

    def list_members(self) -> list[QaMember]:
        return self.store.list_members()

    def add_member(self, name: str, role: str) -> list[QaMember]:
        return self.store.upsert_member(name, role)

    def set_member_role(self, member_id: str, role: str) -> list[QaMember]:
        return self.store.set_member_role(member_id, role)

    def delete_member(self, member_id: str) -> list[QaMember]:
        return self.store.delete_member(member_id)

    # ---------- URL ----------

    def _lock_url(self, raw: str) -> str:
        """空地址允许先建项目；一旦填写必须过 url_guard。"""
        text = (raw or "").strip()
        if not text:
            return ""
        settings = get_settings()
        try:
            return validate_base_url(
                text, allow_local=bool(settings.e2e_allow_local)
            )
        except E2EUrlError:
            p = urlparse(text if "://" in text else "https://" + text)
            origin = f"{p.scheme}://{p.netloc}"
            return validate_base_url(
                origin, allow_local=bool(settings.e2e_allow_local)
            )
