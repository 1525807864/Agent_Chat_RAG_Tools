"""executor 拼目标元数据：不得对 str 调用 append。"""

from __future__ import annotations

from application.ops.executor import _enrich_message
from application.ops.targets import OpsTarget


def _fake_target(**kwargs) -> OpsTarget:
    base = dict(
        id="tgt_abc",
        tenant_id="default",
        name="本平台",
        target_type="platform",
        enabled=True,
        default_namespace="nexora",
        endpoint_base=None,
        auth_token=None,
        kubeconfig=None,
        notes=None,
        created_by="admin",
        created_at="",
        updated_at="",
    )
    base.update(kwargs)
    return OpsTarget(**base)


def test_enrich_message_appends_meta_block():
    out = _enrich_message("有哪些不健康的 Pod？", _fake_target())
    assert out.startswith("有哪些不健康的 Pod？")
    assert "targetId=tgt_abc" in out
    assert "defaultNamespace=nexora" in out
    assert "[Nexora Ops Target]" in out
