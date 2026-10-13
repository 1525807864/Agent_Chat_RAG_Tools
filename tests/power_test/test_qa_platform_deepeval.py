# ============================================================================
# test_qa_platform_deepeval.py
# 测试平台评测：
# 1) 项目 / 用例 / 成员 / 助手规则改稿 —— pytest 硬断言（不花裁判费）
# 2) QA 助手第一期不调 LLM，故不做 GEval；UI Agent 有 LLM 时可另开用例
#
# 运行：
#   pytest tests/power_test/test_qa_platform_deepeval.py -v -s
# ============================================================================

from __future__ import annotations

from pathlib import Path

import pytest

from application.qa.service import QaApplication
from infrastructure.qa.filesystem import QaFileStore


def test_qa_project_case_member_roundtrip(tmp_path: Path):
    """【QA 核心】创建项目 → 生成用例 → 成员 → 删除。"""
    # 租户数据落到 pytest 临时目录，互不污染
    app = QaApplication("deepeval_qa")
    app.store = QaFileStore("deepeval_qa", root=tmp_path)

    # 创建项目（base_url 可空；填写时会过 url_guard）
    p = app.create_project("DeepevalDemo", "", "冒烟目标")
    assert p.id, "项目应有 id"
    assert p.name == "DeepevalDemo"

    # 模板生成用例树
    cases = app.generate_cases(p.id)
    assert len(cases) >= 1, "应至少生成一条用例"
    assert cases[0].code, "用例应有编号"

    # 成员权限
    members = app.add_member("bob", "Bob", "view")
    assert any(m.name == "Bob" for m in members)

    # 删除项目后列表为空
    app.delete_project(p.id)
    assert app.list_projects() == []


def test_qa_assistant_rule_edit(tmp_path: Path):
    """【QA 助手】规则改稿（非 LLM）：选中用例后应把修订写入 fused。"""
    app = QaApplication("deepeval_qa_asst")
    app.store = QaFileStore("deepeval_qa_asst", root=tmp_path)

    p = app.create_project("AsstDemo", "", "goal")
    cases = app.generate_cases(p.id)
    assert cases, "需要有用例才能测助手"
    case_id = cases[0].id

    # 未选中用例：应提示先选中
    empty_pick = app.apply_assistant(p.id, None, "改个标题")
    assert "选中" in empty_pick["reply"]

    # 选中后写入融合需求
    out = app.apply_assistant(p.id, case_id, "把前置条件改成已登录")
    assert out["selected_id"] == case_id
    assert "修订" in out["reply"] or "融合" in out["reply"]

    # 落盘后 fused 应包含助手修订标记
    saved = app.store.list_cases(p.id)
    target = next(c for c in saved if c.id == case_id)
    assert "[助手修订]" in target.fused
    assert "已登录" in target.fused


@pytest.mark.asyncio
async def test_qa_ui_agent_geval_placeholder():
    """【QA UI Agent】有真实 LLM 目标时再开 GEval。

    ui_agent.iter_agent_ui 需要可访问的目标站与 Playwright，成本高；
    默认 skip，避免 CI / 日常 power_test 误跑。
    手工开启：去掉 skip，并准备 DEEPSEEK_API_KEY + 可测 URL。
    """
    pytest.skip(
        "UI Agent 依赖外网目标与 Playwright；"
        "需要评测时去掉 skip，并对最终自然语言步骤用 GEval"
    )

    # ---- 开启后示例骨架（按你们 ui_agent API 接线）----
    # from tests.power_test.deepeval_harness import (
    #     clip, make_geval, measure_ok,
    # )
    # from deepeval.test_case import LLMTestCase
    # # 收集 agent 最终说明文本 actual = ...
    # metric = make_geval(
    #     name="QaUiAgentGoal",
    #     criteria="步骤描述应服务于用户目标，不胡编无关操作。",
    #     threshold=0.55,
    # )
    # await measure_ok(
    #     metric,
    #     LLMTestCase(input="打开首页并搜索天气", actual_output=clip(actual)),
    # )
