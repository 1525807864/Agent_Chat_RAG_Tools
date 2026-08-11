"""会话与消息领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class ChatMessage:
    """单条对话消息（值对象）。"""

    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}
