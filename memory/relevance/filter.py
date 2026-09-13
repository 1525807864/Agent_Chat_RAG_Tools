"""子系统 B：相关性筛选
决定「本轮」哪些 Memdir 条目进入 prompt。
第一期用轻量打分（关键词重叠 + kind 权重）。
"""
from __future__ import annotations

import re
from typing import Any


def _tokenize(text: str) -> set[str]:
    """简单分词。"""
    text = (text or "").lower()
    parts = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,4}", text)
    return {p for p in parts if p}


class RelevanceFilter:
    """输入：query + 候选条目；输出：排序后的 top_k 条目。"""

    KIND_WEIGHT = {
        "solip": 1.4,
        "open_loop": 1.3,
        "preference": 1.2,
        "summary": 1.1,
        "entity": 1.0,
        "fact": 1.0,
    }

    def select(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        top_k: int = 6,
        min_score: float = 0.05,
    ) -> list[dict[str, Any]]:
        q_tokens = _tokenize(query)
        scored: list[tuple[float, dict]] = []

        for item in candidates:
            text = str(item.get("text") or "")
            tags = item.get("tags") or []
            kind = str(item.get("kind") or "fact")
            hint = float(item.get("score_hint") or 0.5)
            t_tokens = _tokenize(text + " " + " ".join(map(str, tags)))
            if not q_tokens:
                overlap = 0.0
            else:
                overlap = len(q_tokens & t_tokens) / max(1, len(q_tokens))

            kind_w = self.KIND_WEIGHT.get(kind, 1.0)
            score = (0.65 * overlap + 0.35 * hint) * kind_w
            # solip 保底，方便下一问假设进入上下文
            if kind == "solip":
                score = max(score, 0.25 * hint * kind_w)

            if score >= min_score:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:top_k]]

    def format_for_prompt(self, items: list[dict[str, Any]]) -> str:
        """把选中条目格式化为 system 可注入的文本块。"""
        if not items:
            return ""
        lines = ["【相关记忆 / Solip 假设】（仅供参考，非用户原话）"]
        for i, it in enumerate(items, start=1):
            kind = it.get("kind", "fact")
            text = (it.get("text") or "").strip()
            meta = it.get("meta") or {}
            # 下一问在 meta.next_questions（写入 solip 时的约定）
            nq = meta.get("next_questions") or it.get("next_questions") or []
            lines.append(f"{i}. ({kind}) {text}")
            if nq:
                lines.append("   可能的下一问：")
                for q in nq[:5]:
                    if isinstance(q, dict):
                        lines.append(
                            f"   - [{q.get('confidence', '?')}] {q.get('question', '')}"
                        )
                    else:
                        lines.append(f"   - {q}")
        return "\n".join(lines)
