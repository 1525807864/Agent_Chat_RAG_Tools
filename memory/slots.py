"""会话级「实体槽位」——对齐 Mem0/Zep 的 structured state。

商业用途：
- 跟进句改写优先读槽位（地点/日期/人名），不依赖关键词召回碰运气
- 写入 memdir 固定 id=session-slots，进程重启可恢复
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SessionSlots:
    """可序列化槽位；只存「可复用事实」，不存整段对话。"""

    # 用户明确提到的地点（北京、上海…）
    location: str = ""
    # 时区/日期偏好（可选）
    timezone: str = ""
    # 称呼、语言偏好等
    preferences: dict[str, str] = field(default_factory=dict)
    # 最近提到的专有名词（产品名、人名），FIFO 截断
    entities: list[str] = field(default_factory=list)
    # schema 版本，便于以后迁移
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SessionSlots":
        if not data:
            return cls()
        return cls(
            location=str(data.get("location") or ""),
            timezone=str(data.get("timezone") or ""),
            preferences=dict(data.get("preferences") or {}),
            entities=list(data.get("entities") or [])[:20],
            version=int(data.get("version") or 1),
        )

    def merge_from_extraction(self, extracted: dict[str, Any]) -> None:
        """用抽取结果合并；空值不覆盖已有槽位（商业：防模型幻觉清空）。"""
        loc = str(extracted.get("location") or "").strip()
        if loc:
            self.location = loc
        for k, v in (extracted.get("preferences") or {}).items():
            if v:
                self.preferences[str(k)] = str(v)
        for e in extracted.get("entities") or []:
            e = str(e).strip()
            if e and e not in self.entities:
                self.entities.append(e)
        self.entities = self.entities[-20:]