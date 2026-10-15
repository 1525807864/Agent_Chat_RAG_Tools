"""测试工作台 HTTP API。全部要登录；写/执行按 RBAC 拦截；响应 camelCase。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from api.auth.deps import AuthUser, get_current_user
from api.auth.user_store import create_user, get_user
from application.qa.rbac import me_payload, require_member, require_qa_perm
from application.qa.report_export import export_bytes
from application.qa.serialize import case_out, member_out, project_out, run_out
from application.qa.service import QaApplication
from domain.qa import ALLOWED_ROLES
from e2e.url_guard import E2EUrlError
from utils.logger import get_logger

router = APIRouter(prefix="/api/qa", tags=["qa"])
_log = get_logger("nexora.qa")


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


class InviteMemberBody(BaseModel):
    """Admin 给本租户开账号：用户名即登录账号，写入同一 tenant_id。"""

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=256)
    role: str = Field(default="view")
    name: str = Field(default="", max_length=40)  # 展示名，空则用 username


class MemberRoleBody(BaseModel):
    role: str


class AssistantBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    case_id: str | None = None


# ---------- 当前身份 ----------


@router.get("/me")
async def qa_me(user: AuthUser = Depends(get_current_user)):
    """前端用来隐藏「编辑 / 邀请」按钮。首次访问会 bootstrap 成 admin。"""
    return me_payload(user)


# ---------- 项目 ----------


@router.get("/projects")
async def list_projects(user: AuthUser = Depends(get_current_user)):
    require_member(user)
    return {"items": [project_out(p) for p in _app(user).list_projects()]}


@router.post("/projects")
async def create_project(
    body: CreateProjectBody,
    user: AuthUser = Depends(require_qa_perm("project:write")),
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
    require_member(user)
    try:
        return project_out(_app(user).get_project(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None


@router.patch("/projects/{project_id}")
async def patch_project(
    project_id: str,
    body: PatchProjectBody,
    user: AuthUser = Depends(require_qa_perm("project:write")),
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
    project_id: str,
    user: AuthUser = Depends(require_qa_perm("project:delete")),
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
    user: AuthUser = Depends(require_qa_perm("project:write")),
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
    require_member(user)
    try:
        items = _app(user).list_cases(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return {"items": [case_out(c) for c in items]}


@router.post("/projects/{project_id}/generate")
async def generate_cases(
    project_id: str,
    body: GenerateBody,
    user: AuthUser = Depends(require_qa_perm("case:write")),
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
    user: AuthUser = Depends(require_qa_perm("case:write")),
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
    user: AuthUser = Depends(require_qa_perm("case:write")),
):
    try:
        items = _app(user).delete_case(project_id, case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="用例或项目不存在") from None
    return {"items": [case_out(c) for c in items]}


# ---------- 运行 ----------


@router.get("/projects/{project_id}/runs")
async def list_runs(project_id: str, user: AuthUser = Depends(get_current_user)):
    require_member(user)
    try:
        items = _app(user).list_runs(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return {"items": [run_out(r) for r in items]}


@router.post("/projects/{project_id}/runs")
async def run_smoke(
    project_id: str,
    body: RunBody,
    user: AuthUser = Depends(require_qa_perm("run:execute")),
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
    user: AuthUser = Depends(require_qa_perm("run:execute")),
):
    """SSE：每步一条 data JSON，最后一条 type=done（含落盘后的 run）。"""
    app = _app(user)

    _log.info(
        "QA UI 运行开始 project_id=%s tenant_id=%s user=%s base_url=%s",
        project_id,
        user.tenant_id,
        user.user_id,
        (body.base_url or "")[:120],
    )

    async def _gen():
        try:
            async for ev in app.iter_ui_run(
                project_id,
                name=body.name,
                base_url=body.base_url,
                goal=body.goal,
            ):
                if isinstance(ev, dict) and ev.get("type") in (
                    "done",
                    "error",
                    "step",
                ):
                    _log.debug(
                        "QA UI 事件 project_id=%s type=%s",
                        project_id,
                        ev.get("type"),
                    )
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            _log.info("QA UI 运行结束 project_id=%s", project_id)
        except FileNotFoundError:
            _log.warning("QA UI 项目不存在 project_id=%s", project_id)
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
            _log.warning(
                "QA UI URL 校验失败 project_id=%s detail=%s",
                project_id,
                exc,
            )
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
            _log.warning(
                "QA UI 参数错误 project_id=%s detail=%s", project_id, exc
            )
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
            _log.exception(
                "QA UI 运行异常 project_id=%s: %s", project_id, exc
            )
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
    require_member(user)
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
    user: AuthUser = Depends(require_qa_perm("case:write")),
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


# ---------- 成员（SaaS 用户配置）----------


@router.get("/members")
async def list_members(user: AuthUser = Depends(get_current_user)):
    require_member(user)
    return {"items": [member_out(m) for m in _app(user).list_members()]}


@router.post("/members")
async def invite_member(
    body: InviteMemberBody,
    user: AuthUser = Depends(require_qa_perm("member:manage")),
):
    """邀请团队成员进入当前租户。

    - 用户不存在：create_user(..., tenant_id=当前租户)
    - 已在本租户：只写入/更新 QA 角色，不改密码
    - 已在别的租户：拒绝，避免串租户
    """
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="非法角色")
    username = body.username.strip()
    existing = get_user(username)
    if existing is None:
        try:
            create_user(username, body.password, tenant_id=user.tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif existing.tenant_id != user.tenant_id:
        raise HTTPException(status_code=409, detail="该用户已属于其他租户")
    display = (body.name or "").strip() or username
    try:
        items = _app(user).add_member(username, display, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [member_out(m) for m in items]}


@router.patch("/members/{member_id}")
async def patch_member(
    member_id: str,
    body: MemberRoleBody,
    user: AuthUser = Depends(require_qa_perm("member:manage")),
):
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="非法角色")
    try:
        items = _app(user).set_member_role(member_id, body.role)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="成员不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [member_out(m) for m in items]}


@router.delete("/members/{member_id}")
async def delete_member(
    member_id: str,
    user: AuthUser = Depends(require_qa_perm("member:manage")),
):
    try:
        items = _app(user).delete_member(member_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="成员不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [member_out(m) for m in items]}
