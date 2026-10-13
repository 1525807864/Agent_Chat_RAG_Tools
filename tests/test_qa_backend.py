"""测试平台后端：落盘 / 生成 / 删除 / 成员 / 旧 JSON 兼容。"""

from __future__ import annotations

from pathlib import Path

from application.qa.serialize import case_out, member_out, project_out
from application.qa.service import QaApplication
from infrastructure.qa.filesystem import QaFileStore


def test_qa_roundtrip(tmp_path: Path) -> None:
    app = QaApplication("demo")
    app.store = QaFileStore("demo", root=tmp_path)

    p = app.create_project("Demo", "", "goal")
    assert "baseUrl" in project_out(p)
    assert p.source_docs == []

    cases = app.generate_cases(p.id)
    assert cases[0].code == "1"
    assert cases[1].code == "1.1"
    assert "projectId" in case_out(cases[0])

    # 删根带走子节点
    left = app.delete_case(p.id, cases[0].id)
    assert left == []

    members = app.add_member("alice", "Alice", "view")
    assert any(m.user_id == "alice" and m.role == "view" for m in members)
    assert "userId" in member_out(members[0])

    app.delete_project(p.id)
    assert app.list_projects() == []


def test_old_project_json_without_source_docs(tmp_path: Path) -> None:
    store = QaFileStore("old", root=tmp_path)
    pid = "abc123def456"
    d = tmp_path / "old" / pid
    d.mkdir(parents=True)
    (d / "project.json").write_text(
        '{"id":"abc123def456","tenant_id":"old","name":"x",'
        '"base_url":"","goal":"","created_at":"t"}',
        encoding="utf-8",
    )
    g = store.get_project(pid)
    assert g.source_docs == []
