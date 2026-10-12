"""把项目/用例/运行落在 data/qa/{tenant}/{project_id}/，按租户隔离。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from domain.qa import QaCase, QaMember, QaProject, QaRun
from shared.path_security import get_project_root
from shared.timeutil import now_iso as _now


def _sid() -> str:
    """12 位 hex，当目录名/主键。"""
    return uuid4().hex[:12]


def _project_from_raw(raw: dict) -> QaProject:
    """旧文件没有 source_docs 时补空列表，避免 dataclass 构造失败。"""
    data = dict(raw)
    data.setdefault("source_docs", [])
    return QaProject(**data)


def _case_from_raw(raw: dict) -> QaCase:
    """旧用例没有 code / source_doc_ids 时补默认。"""
    data = dict(raw)
    data.setdefault("code", "")
    data.setdefault("source_doc_ids", [])
    # 兼容早期手写字段名
    if "requirement" not in data and "req" in data:
        data["requirement"] = data.pop("req")
    return QaCase(**data)


def _run_from_raw(raw: dict) -> QaRun:
    """运行记录缺 artifacts 时补空 dict。"""
    data = dict(raw)
    data.setdefault("artifacts", {})
    data.setdefault("created_at", "")
    return QaRun(**data)


class QaFileStore:
    """一个租户一份根目录。"""

    def __init__(self, tenant_id: str, root: Path | None = None) -> None:
        tid = (tenant_id or "default").strip() or "default"
        base = root or (get_project_root() / "data" / "qa")
        self._dir = base / tid
        self._dir.mkdir(parents=True, exist_ok=True)

    def _proj_dir(self, project_id: str) -> Path:
        """项目目录；id 只允许字母数字和短横线。"""
        pid = "".join(c for c in project_id if c.isalnum() or c == "-")
        if not pid:
            raise ValueError("非法 project_id")
        return self._dir / pid

    def _read_json(self, path: Path, default: Any) -> Any:
        """文件不存在返回 default。"""
        if not path.is_file():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, data: Any) -> None:
        """原子一点：先写 tmp 再替换。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ---------- 项目 ----------

    def list_projects(self) -> list[QaProject]:
        """扫描租户下所有 project.json。"""
        items: list[QaProject] = []
        if not self._dir.is_dir():
            return items
        for child in sorted(self._dir.iterdir()):
            if not child.is_dir():
                continue
            meta = child / "project.json"
            if not meta.is_file():
                continue
            raw = self._read_json(meta, {})
            if isinstance(raw, dict) and raw.get("id"):
                items.append(_project_from_raw(raw))
        return items

    def create_project(self, *, name: str, base_url: str, goal: str) -> QaProject:
        """新建项目。"""
        proj = QaProject(
            id=_sid(),
            tenant_id=self._dir.name,
            name=(name or "未命名项目").strip()[:80],
            base_url=(base_url or "").strip()[:512],
            goal=(goal or "").strip()[:2000],
            created_at=_now(),
            source_docs=[],
        )
        d = self._proj_dir(proj.id)
        self._write_json(d / "project.json", proj.__dict__)
        self._write_json(d / "cases.json", [])
        return proj

    def get_project(self, project_id: str) -> QaProject:
        """读取单个项目，没有就抛 FileNotFoundError。"""
        path = self._proj_dir(project_id) / "project.json"
        raw = self._read_json(path, None)
        if not raw:
            raise FileNotFoundError(project_id)
        return _project_from_raw(raw)

    def save_project(self, proj: QaProject) -> None:
        """更新 name / base_url / goal / source_docs。"""
        self._write_json(self._proj_dir(proj.id) / "project.json", proj.__dict__)

    def delete_project(self, project_id: str) -> None:
        """删除项目目录（含 cases.json、runs/）。不存在则幂等成功。"""
        d = self._proj_dir(project_id)
        if d.is_dir():
            shutil.rmtree(d)

    def add_source_doc(self, project_id: str, doc: dict[str, Any]) -> QaProject:
        """把资料摘要挂到 project.source_docs。"""
        proj = self.get_project(project_id)
        docs = list(proj.source_docs or [])
        docs.append(doc)
        proj.source_docs = docs
        self.save_project(proj)
        return proj

    # ---------- 用例 ----------

    def list_cases(self, project_id: str) -> list[QaCase]:
        """该项目全部用例。"""
        raw = self._read_json(self._proj_dir(project_id) / "cases.json", [])
        if not isinstance(raw, list):
            return []
        return [_case_from_raw(item) for item in raw if isinstance(item, dict)]

    def save_cases(self, project_id: str, cases: list[QaCase]) -> None:
        """整表覆盖写回（第一期数据量小）。"""
        payload = [c.__dict__ for c in cases]
        self._write_json(self._proj_dir(project_id) / "cases.json", payload)

    def add_cases(self, project_id: str, extra: list[QaCase]) -> list[QaCase]:
        """追加生成结果。"""
        all_cases = self.list_cases(project_id) + extra
        self.save_cases(project_id, all_cases)
        return all_cases

    def patch_case(self, project_id: str, case_id: str, **fields: Any) -> QaCase:
        """确认/编辑单条。"""
        cases = self.list_cases(project_id)
        found: QaCase | None = None
        for c in cases:
            if c.id == case_id:
                for k, v in fields.items():
                    if v is not None and hasattr(c, k):
                        setattr(c, k, v)
                found = c
                break
        if found is None:
            raise FileNotFoundError(case_id)
        self.save_cases(project_id, cases)
        return found

    def delete_case(self, project_id: str, case_id: str) -> list[QaCase]:
        """
        删除一条用例；若有子节点（parent_id 指向它）一并删除。
        返回删除后的完整列表。
        """
        cases = self.list_cases(project_id)
        to_drop = {case_id}
        changed = True
        while changed:
            changed = False
            for c in cases:
                if c.parent_id in to_drop and c.id not in to_drop:
                    to_drop.add(c.id)
                    changed = True
        remain = [c for c in cases if c.id not in to_drop]
        if len(remain) == len(cases):
            raise FileNotFoundError(case_id)
        self.save_cases(project_id, remain)
        return remain

    # ---------- 运行 ----------

    def add_run(self, run: QaRun) -> QaRun:
        """写入一次执行。"""
        path = self._proj_dir(run.project_id) / "runs" / f"{run.id}.json"
        self._write_json(path, run.__dict__)
        return run

    def list_runs(self, project_id: str) -> list[QaRun]:
        """按文件名倒序，最多 50 条。"""
        d = self._proj_dir(project_id) / "runs"
        if not d.is_dir():
            return []
        items: list[QaRun] = []
        for f in sorted(d.glob("*.json"), reverse=True):
            raw = self._read_json(f, {})
            if isinstance(raw, dict) and raw.get("id"):
                items.append(_run_from_raw(raw))
        return items[:50]

    def get_run(self, project_id: str, run_id: str) -> QaRun:
        """读取单次运行；id 过滤防路径穿越。"""
        rid = "".join(c for c in run_id if c.isalnum())
        if not rid:
            raise ValueError("非法 run_id")
        path = self._proj_dir(project_id) / "runs" / f"{rid}.json"
        raw = self._read_json(path, None)
        if not isinstance(raw, dict) or not raw.get("id"):
            raise FileNotFoundError(run_id)
        return _run_from_raw(raw)

    # ---------- 成员（租户级 members.json）----------

    def _members_path(self) -> Path:
        return self._dir / "members.json"

    def list_members(self) -> list[QaMember]:
        """没有文件时返回当前租户名一条 admin。"""
        raw = self._read_json(self._members_path(), None)
        if not raw or not isinstance(raw, list):
            return [QaMember(id="me", name=self._dir.name, role="admin")]
        return [QaMember(**m) for m in raw if isinstance(m, dict) and m.get("id")]

    def save_members(self, members: list[QaMember]) -> None:
        self._write_json(self._members_path(), [m.__dict__ for m in members])

    def upsert_member(self, name: str, role: str) -> list[QaMember]:
        """按 name 更新角色；没有则追加。"""
        members = self.list_members()
        clean = (name or "").strip()[:40]
        if not clean:
            raise ValueError("成员名不能为空")
        for m in members:
            if m.name == clean:
                m.role = role
                self.save_members(members)
                return members
        members.append(QaMember(id=_sid(), name=clean, role=role))
        self.save_members(members)
        return members

    def set_member_role(self, member_id: str, role: str) -> list[QaMember]:
        members = self.list_members()
        for m in members:
            if m.id == member_id:
                m.role = role
                self.save_members(members)
                return members
        raise FileNotFoundError(member_id)

    def delete_member(self, member_id: str) -> list[QaMember]:
        """删除成员；至少保留一名 admin。"""
        before = self.list_members()
        members = [m for m in before if m.id != member_id]
        if len(members) == len(before):
            raise FileNotFoundError(member_id)
        if not any(m.role == "admin" for m in members):
            raise ValueError("不能删除最后一个管理员")
        self.save_members(members)
        return members
