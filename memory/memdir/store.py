"""
memdirstore 读写 json 记忆文件
条目结构（单条 memory item）约定：
{
  "id": "uuid",
  "kind": "preference" | "fact" | "open_loop" | "entity" | "solip" | "summary",
  "text": "自然语言内容",
  "score_hint": 0.0~1.0,
  "tags": ["nasdaq", "..."],
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "meta": {}
}
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory.memdir.paths import (
    default_memdir_path,
    project_memdir_path,
    session_memdir_file,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_doc() -> dict[str, Any]:
    """文件不存在时的空文档骨架。"""
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "items": [],
    }


class MemdirStore:
    """子系统 A 实现：基于 JSON 文件的记忆目录。"""

    def __init__(self, root: Path | None = None, project_root: Path | None = None):
        if root is not None:
            self.root = Path(root).resolve()
        elif project_root is not None:
            self.root = default_memdir_path(Path(project_root))
        else:
            self.root = Path("data/memdir").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # 与 paths.session_memdir_file 一致：sessions/
        (self.root / "sessions").mkdir(parents=True, exist_ok=True)

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return _empty_doc()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # 注意字段名是 items（复数）
            if not isinstance(data, dict) or "items" not in data:
                return _empty_doc()
            return data
        except Exception:
            return _empty_doc()

    def _write(self, path: Path, doc: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc["updated_at"] = _now_iso()
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_project_items(self) -> list[dict[str, Any]]:
        return list(self._read(project_memdir_path(self.root)).get("items", []))

    def load_session_items(self, session_id: str) -> list[dict[str, Any]]:
        """读取某会话级全部条目。"""
        return list(
            self._read(session_memdir_file(self.root, session_id)).get("items", [])
        )

    def upsert_session_item(
        self,
        session_id: str,
        *,
        kind: str,
        text: str,
        tags: list[str] | None = None,
        score_hint: float = 0.5,
        meta: dict | None = None,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        path = session_memdir_file(self.root, session_id)
        doc = self._read(path)
        items: list[dict] = doc.setdefault("items", [])
        now = _now_iso()
        iid = item_id or str(uuid.uuid4())

        for it in items:
            if it.get("id") == iid:
                it["kind"] = kind
                it["text"] = text
                it["tags"] = tags or []
                it["score_hint"] = score_hint
                it["meta"] = meta or {}
                it["updated_at"] = now
                self._write(path, doc)
                self._mirror_mysql(
                    session_id=session_id,
                    kind=kind,
                    text=text,
                    tags=tags,
                    score_hint=score_hint,
                    meta=meta,
                    item_id=iid,
                )
                return it

        new_item = {
            "id": iid,
            "kind": kind,
            "text": text,
            "tags": tags or [],
            "score_hint": score_hint,
            "meta": meta or {},
            "created_at": now,
            "updated_at": now,
        }
        items.append(new_item)
        if len(items) > 1000:
            doc["items"] = items[-1000:]
        self._write(path, doc)
        self._mirror_mysql(
            session_id=session_id,
            kind=kind,
            text=text,
            tags=tags,
            score_hint=score_hint,
            meta=meta,
            item_id=iid,
        )
        return new_item

    def _mirror_mysql(
        self,
        *,
        session_id: str | None,
        kind: str,
        text: str,
        tags: list[str] | None,
        score_hint: float,
        meta: dict | None,
        item_id: str,
    ) -> None:
        """P2：双写 MySQL memory_items（失败忽略）。"""
        try:
            from infrastructure.db.memory_items_store import upsert_memory_item

            tenant_id = "default"
            if session_id and "__" in session_id:
                tenant_id = session_id.split("__", 1)[0] or "default"
            upsert_memory_item(
                tenant_id=tenant_id,
                session_id=session_id,
                kind=kind,
                text=text,
                origin=str((meta or {}).get("origin") or "agent"),
                tags=tags,
                score_hint=score_hint,
                meta=meta,
                item_id=item_id,
            )
        except Exception:
            pass

    def upsert_project_item(self, **kwargs) -> dict[str, Any]:
        """项目级 upsert（与 session 对称，供偏好沉淀使用）。"""
        path = project_memdir_path(self.root)
        doc = self._read(path)
        items: list[dict] = doc.setdefault("items", [])
        now = _now_iso()
        iid = kwargs.get("item_id") or str(uuid.uuid4())
        kind = kwargs.get("kind", "fact")
        text = kwargs.get("text", "")
        tags = kwargs.get("tags") or []
        score_hint = float(kwargs.get("score_hint", 0.5))
        meta = kwargs.get("meta") or {}

        for it in items:
            if it.get("id") == iid:
                it.update(
                    {
                        "kind": kind,
                        "text": text,
                        "tags": tags,
                        "score_hint": score_hint,
                        "meta": meta,
                        "updated_at": now,
                    }
                )
                self._write(path, doc)
                self._mirror_mysql(
                    session_id=None,
                    kind=kind,
                    text=text,
                    tags=tags,
                    score_hint=score_hint,
                    meta=meta,
                    item_id=iid,
                )
                return it

        new_item = {
            "id": iid,
            "kind": kind,
            "text": text,
            "tags": tags,
            "score_hint": score_hint,
            "meta": meta,
            "created_at": now,
            "updated_at": now,
        }
        items.append(new_item)
        if len(items) > 1000:
            doc["items"] = items[-1000:]
        self._write(path, doc)
        self._mirror_mysql(
            session_id=None,
            kind=kind,
            text=text,
            tags=tags,
            score_hint=score_hint,
            meta=meta,
            item_id=iid,
        )
        return new_item
