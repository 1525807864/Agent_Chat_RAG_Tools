"""Intent Guard 的三个 LLM 协议模板（风格对齐 Solip：中文、只输出 JSON）。"""

ALIGNMENT_CHECK_PROMPT = """你是目标对齐检查器。判断 Agent 准备执行的下一步动作是否服务于用户的原始目标。
要求：
1. 只输出 JSON（不要 Markdown 代码围栏）。
2. JSON schema:
{{
  "verdict": "aligned | drift | irrelevant",
  "reason": "一句话判断理由，40字以内",
  "correction": "仅 verdict=drift 时填写：给 Agent 的一句纠正指令，指明应回到哪个目标或子任务；其余填空字符串"
}}
3. 判定标准：
- aligned：动作服务于【用户目标】或【任务清单】中未完成的任务；
- drift：动作明显偏离目标，正在做用户没要求的事（例如目标是写报告却去查无关新闻）；
- irrelevant：与目标无关但无害（澄清、闲聊）。
4. 不要被动作细节迷惑，只判断「这一步是否朝着目标前进」。
【用户目标】
{anchor_goal}
【任务清单】
{checklist}
【本轮用户请求】
{user_task}
【Agent 本步决策】
Thought: {thought}
Action: {action_name}
Action Input: {action_input}
"""

COMPLETENESS_PROMPT = """你是任务完整性校验器。根据助手刚给出的回答，更新任务清单的完成状态。
要求：
1. 只输出 JSON（不要 Markdown 代码围栏）。
2. JSON schema:
{{
  "verdict": "complete | partial | not_started",
  "task_updates": [{{"id": "任务id", "status": "done | blocked", "note": "30字以内说明"}}],
  "new_tasks": [{{"title": "新发现但未完成的子任务", "note": "30字以内说明"}}],
  "open_summary": "verdict 不为 complete 时的一句话未完成说明；否则空字符串"
}}
3. 规则：
- 只有回答内容明确完成的任务才标 done，绝不虚构闭环；
- 用户明确表示放弃或搁置的任务标 blocked；
- new_tasks 最多 {max_new} 条，回答中没发现新任务就给空数组；
- verdict=complete 表示清单中所有任务都已完成。
【用户目标】
{anchor_goal}
【任务清单】
{checklist}
【本轮用户请求】
{user_input}
【助手回答】
{answer}
"""

DECOMPOSE_PROMPT = """你是任务拆解器。把用户的总目标拆成带依赖的子任务图，而不是并列待办。
要求：
1. 只输出 JSON（不要 Markdown 代码围栏）。
2. JSON schema:
{{
  "tasks": [
    {{
      "id": "t1",
      "title": "子任务描述（动宾结构，简洁）",
      "depends_on": [],
      "acceptance": "怎样才算完成，20字以内"
    }}
  ]
}}
3. 最多 {max_tasks} 条，id 用 t1、t2…；depends_on 只引用已出现的 id。
4. 无先后关系时 depends_on 给空数组；后一步必须等前一步时再写依赖。
5. 目标简单时 1 条即可。
【用户目标】
{goal}
"""