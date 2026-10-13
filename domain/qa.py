"""测试工作台领域对象：与前端 types/qa.ts 语义对齐。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ---------- 用例类型常量（与前端 QaKind 一致）----------
KIND_FUNCTIONAL = "functional"
KIND_API = "api"
KIND_BLACKBOX = "blackbox"
KIND_PERF = "performance"
KIND_SECURITY = "security"
KIND_COMPAT = "compat"

# ---------- 成员角色（仅本租户内有效）----------
# admin   : 可管理项目 / 编辑用例 / 邀请成员 / 执行
# execute : 只能执行用例，不能改用例、不能管成员
# view    : 只读
ROLE_ADMIN = "admin"
ROLE_EXECUTE = "execute"
ROLE_VIEW = "view"
ALLOWED_ROLES = frozenset({ROLE_ADMIN, ROLE_EXECUTE, ROLE_VIEW})

@dataclass
class QaSourceDoc:
    """项目资料：上传 PDF/md 或粘贴 URL 后的摘要，给中栏/助手用。"""
    id: str
    name: str
    kind: str  # docx | pdf | md | url | text
    excerpt: str = ""  # 前几百字摘要，列表卡片展示
    # 第一期可不落 rows；需要「需求表」时再加 list[dict]


@dataclass
class QaProject:
    """一个测试项目 = 被测环境 + 目标 + 资料。"""
    id: str
    tenant_id: str
    name: str
    base_url: str
    goal: str = ""
    created_at: str = ""
    # 新增：与前端 sourceDocs 对齐；旧 JSON 没有时反序列化要给默认 []
    source_docs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class QaCase:
    """测试树节点：parent_id=None 为需求包根。"""
    id: str
    project_id: str
    parent_id: Optional[str]
    title: str
    kind: str
    requirement: str
    fused: str
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    status: str = "draft"  # draft | confirmed | ready | passed | failed
    # 新增：树展示编号，如 "1" / "1.2"；旧数据没有时由 service 补
    code: str = ""
    # 新增：关联资料 id 列表
    source_doc_ids: list[str] = field(default_factory=list)


@dataclass
class QaRun:
    """一次执行记录：verdict 必须来自 runner，禁止 LLM 自判。"""
    id: str
    project_id: str
    case_ids: list[str]
    verdict: str  # pass | fail | error
    summary: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class QaMember:
    """租户内一名真实登录用户的 QA 角色。

    user_id 必须等于 JWT 的 sub（登录用户名）。
    旧数据可能没有 user_id，反序列化时给空串，由 bootstrap 补齐。
    """
    id: str
    name: str
    role: str  # admin | execute | view
    user_id: str = ""  # 登录账号，首次进入会写成当前用户