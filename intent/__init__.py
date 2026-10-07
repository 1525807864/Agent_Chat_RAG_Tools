"""意图守卫（Intent Guard）：意图追踪与任务完整性维护。

在 Agent 每一步决策前插入轻量「需求对齐检查」，防止执行中的深层发现
（Level 4）覆盖用户最初的目标（Level 1）。

- models：TaskPlan（意图锚点 + 任务清单）数据结构与状态机
- checker：对齐检查 / 完成度校验两个 LLM 协议
- planner：首轮后台任务拆解
- service：IntentGuardService 统一入口（对 Agent 循环与 use case 提供）

原则：fail-open 兜底（guard 关闭/超时/异常时行为与现状完全一致）、
只增不改（Solip 不受影响）、状态单写多读。
"""

from intent.service import IntentGuardService

__all__ = ["IntentGuardService"]
