"""把领域对象转成前端 camelCase JSON，避免 base_url / baseUrl 对不上。"""

from __future__ import annotations

from domain.qa import QaCase, QaMember, QaProject, QaRun


def project_out(p: QaProject) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "baseUrl": p.base_url,
        "goal": p.goal,
        "createdAt": p.created_at,
        "sourceDocs": p.source_docs or [],
        "tenantId": p.tenant_id,
    }


def case_out(c: QaCase) -> dict:
    return {
        "id": c.id,
        "projectId": c.project_id,
        "parentId": c.parent_id,
        "code": c.code or "",
        "title": c.title,
        "kind": c.kind,
        "requirement": c.requirement,
        "fused": c.fused,
        "steps": c.steps or [],
        "expected": c.expected,
        "status": c.status,
        "sourceDocIds": c.source_doc_ids or [],
    }


def run_out(r: QaRun) -> dict:
    return {
        "id": r.id,
        "projectId": r.project_id,
        "caseIds": r.case_ids or [],
        "verdict": r.verdict,
        "summary": r.summary,
        "artifacts": r.artifacts or {},
        "createdAt": r.created_at,
    }


def member_out(m: QaMember) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "role": m.role,
    }
