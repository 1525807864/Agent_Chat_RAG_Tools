# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(r"C:\Users\lee\Desktop\My_Agent\12_REACT_AGENT_DEEP.md")
text = p.read_text(encoding="utf-8")
end_marker = "- `_normalize_tool_input` 处理模型少包一层 / 字符串等脏输入"
eidx = text.find(end_marker)
if eidx < 0:
    raise SystemExit("end marker not found")
head = text[: eidx + len(end_marker)].rstrip()
if head.endswith("'''"):
    head = head[:-3].rstrip()

tail = r'''

## 12.9 `run()` 真实分支（对照源码）

每轮 `think` 之后的判定顺序：

```mermaid
flowchart TD
  T[think + merge usage] --> F{_parse_final_answer?}
  F -->|有| Ret1[立即返回 result]
  F -->|无| A{_parse_action?}
  A -->|有 Action| Exec[ainvoke_tool -> last_tool_result]
  Exec --> Next[下一轮]
  A -->|无 Action| PF[consecutive_parse_failures++]
  PF --> NL{无 Action: 前缀且非空?}
  NL -->|是| Ret2[整段当直接回答返回]
  NL -->|否| Need{has_web_search AND needs_web_search AND 尚未 forced AND 无 tool_calls?}
  Need -->|是| Force[_force_web_search + format_reminder]
  Force --> Next
  Need -->|否| Fail2{failures >= 2?}
  Fail2 -->|是且有 Observation| Ret3[根据工具结果返回]
  Fail2 -->|是| Ret4[返回 thought 原文]
  Fail2 -->|否| Reminder[写入 format_reminder 再 continue]
```

要点：

1. **先 Final**：合法 `Final Answer:` 直接结束（不强制搜）。
2. **自然语言直接答**：无 `Action:` 且已失败>=1 次时，把整段 thought 当答案返回（问候/常识路径）。
3. **强制搜**：仅当需要联网、有 web_search、尚未 forced、尚无 tool_calls、且解析失败时；`_force_web_search` 同步调用并把 Observation 写入 context。
4. **连续失败>=2**：优先用已有 Observation，避免「无法联网」胡话。
5. 超 `max_tool_calls`：若有 Observation 则「根据工具结果」返回，并带 `warning`。

## 12.10 返回字段（完整）

| 键 | 含义 |
|----|------|
| agent / role | 名称与角色 |
| result | 最终文本 |
| tool_calls | 审计列表（可含 forced: true） |
| iterations | 循环轮次 |
| usage | TurnUsage.to_dict() |
| warning | 可选：达最大工具次数等 |
'''

p.write_text(head + "\n" + tail, encoding="utf-8")
print("fixed", p.stat().st_size)
