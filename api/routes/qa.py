"""测试工作台 HTTP API。全部要登录；响应统一 camelCase。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from api.auth.deps import AuthUser, get_current_user
from application.qa.report_export import export_bytes
from application.qa.serialize import case_out, member_out, project_out, run_out
from application.qa.service import QaApplication
from e2e.url_guard import E2EUrlError

router = APIRouter(prefix="/api/qa", tags=["qa"])

_ALLOWED_ROLES = frozenset({"admin", "execute", "view"})


def _app(user: AuthUser) -> QaApplication:
    return QaApplication(user.tenant_id)


class CreateProjectBody(BaseModel):
    name: str = Field(default="新测试项目", max_length=80)
    base_url: str = Field(default="", max_length=512)
    goal: str = Field(default="", max_length=2000)


class PatchProjectBody(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, max_length=512)
    goal: str | None = Field(default=None, max_length=2000)


class GenerateBody(BaseModel):
    goal: str | None = Field(default=None, max_length=2000)


class ConfirmBody(BaseModel):
    fused: str | None = Field(default=None, max_length=8000)


class RunBody(BaseModel):
    case_ids: list[str] | None = None


class UiRunBody(BaseModel):
    """智能 UI 测试：name 给人看，goal 给模型执行。"""

    name: str = Field(default="智能UI测试", max_length=80)
    goal: str = Field(default="", max_length=4000)
    base_url: str = Field(default="", max_length=512)


class MemberBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    role: str = Field(default="view")


class MemberRoleBody(BaseModel):
    role: str


class AssistantBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    case_id: str | None = None

# ---------- 项目 ----------


@router.get("/projects")
async def list_projects(user: AuthUser = Depends(get_current_user)):
    return {"items": [project_out(p) for p in _app(user).list_projects()]}


@router.post("/projects")
async def create_project(
    body: CreateProjectBody, user: AuthUser = Depends(get_current_user)
):
    try:
        p = _app(user).create_project(body.name, body.base_url, body.goal)
    except E2EUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return project_out(p)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: AuthUser = Depends(get_current_user)):
    try:
        return project_out(_app(user).get_project(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


@router.patch("/projects/{project_id}")
async def patch_project(
    project_id: str,
    body: PatchProjectBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        p = _app(user).update_project(
            project_id,
            name=body.name,
            base_url=body.base_url,
            goal=body.goal,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    except E2EUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return project_out(p)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str, user: AuthUser = Depends(get_current_user)
):
    try:
        _app(user).delete_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return {"ok": True}


@router.post("/projects/{project_id}/sources")
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
):
    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    try:
        p = _app(user).add_local_source(
            project_id, file.filename or "upload.txt", text
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return project_out(p)


# ---------- 用例 ----------


@router.get("/projects/{project_id}/cases")
async def list_cases(project_id: str, user: AuthUser = Depends(get_current_user)):
    try:
        items = _app(user).list_cases(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return {"items": [case_out(c) for c in items]}


@router.post("/projects/{project_id}/generate")
async def generate_cases(
    project_id: str,
    body: GenerateBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        items = _app(user).generate_cases(project_id, body.goal)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return {"items": [case_out(c) for c in items]}


@router.post("/projects/{project_id}/cases/{case_id}/confirm")
async def confirm_case(
    project_id: str,
    case_id: str,
    body: ConfirmBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        c = _app(user).confirm_case(project_id, case_id, body.fused)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="用例或项目不存在") from None
    return case_out(c)


@router.delete("/projects/{project_id}/cases/{case_id}")
async def delete_case(
    project_id: str,
    case_id: str,
    user: AuthUser = Depends(get_current_user),
):
    try:
        items = _app(user).delete_case(project_id, case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="用例或项目不存在") from None
    return {"items": [case_out(c) for c in items]}


# ---------- 运行 ----------


@router.get("/projects/{project_id}/runs")
async def list_runs(project_id: str, user: AuthUser = Depends(get_current_user)):
    try:
        items = _app(user).list_runs(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return {"items": [run_out(r) for r in items]}


@router.post("/projects/{project_id}/runs")
async def run_smoke(
    project_id: str,
    body: RunBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        run = _app(user).run_smoke(project_id, body.case_ids)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    except E2EUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run_out(run)


@router.post("/projects/{project_id}/runs/ui")
async def run_ui(
    project_id: str,
    body: UiRunBody,
    user: AuthUser = Depends(get_current_user),
):
    """SSE：每步一条 data JSON，最后一条 type=done（含落盘后的 run）。"""
    app = _app(user)

    async def _gen():
        try:
            async for ev in app.iter_ui_run(
                project_id,
                name=body.name,
                base_url=body.base_url,
                goal=body.goal,
            ):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except FileNotFoundError:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "verdict": "error",
                        "summary": "项目不存在",
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        except E2EUrlError as exc:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "verdict": "error",
                        "summary": str(exc),
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        except ValueError as exc:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "verdict": "error",
                        "summary": str(exc),
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        except Exception as exc:  # noqa: BLE001
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "verdict": "error",
                        "summary": str(exc)[:500],
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/runs/{run_id}/export")
async def export_run(
    project_id: str,
    run_id: str,
    fmt: str = "xlsx",
    user: AuthUser = Depends(get_current_user),
):
    """导出该次运行步骤证据。fmt=xlsx|docx|pdf。"""
    try:
        run = _app(user).get_run(project_id, run_id)
        data, mime, filename = export_bytes(run, fmt)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="运行不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- 助手 ----------


@router.post("/projects/{project_id}/assistant")
async def assistant(
    project_id: str,
    body: AssistantBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        result = _app(user).apply_assistant(project_id, body.case_id, body.text)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目或用例不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "reply": result["reply"],
        "selectedId": result["selected_id"],
        "cases": [case_out(c) for c in result["cases"]],
    }


# ---------- 成员 ----------


@router.get("/members")
async def list_members(user: AuthUser = Depends(get_current_user)):
    return {"items": [member_out(m) for m in _app(user).list_members()]}


@router.post("/members")
async def add_member(
    body: MemberBody, user: AuthUser = Depends(get_current_user)
):
    if body.role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="非法角色")
    try:
        items = _app(user).add_member(body.name, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [member_out(m) for m in items]}


@router.patch("/members/{member_id}")
async def patch_member(
    member_id: str,
    body: MemberRoleBody,
    user: AuthUser = Depends(get_current_user),
):
    if body.role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="非法角色")
    try:
        items = _app(user).set_member_role(member_id, body.role)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="成员不存在") from None
    return {"items": [member_out(m) for m in items]}


@router.delete("/members/{member_id}")
async def delete_member(
    member_id: str, user: AuthUser = Depends(get_current_user)
):
    try:
        items = _app(user).delete_member(member_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="成员不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [member_out(m) for m in items]}
