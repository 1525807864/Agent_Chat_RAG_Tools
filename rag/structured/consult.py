# ============================================================================
# consult.py — 对话状态机（第一期）
# 1. 从用户这句话里补因子
# 2. 还缺高优先级因子 → 只问一个问题，先不检索
# 3. 关键因子够了 → 调用方传入的 retrieve_fn 拿原文，再让模型回答
# ============================================================================

from __future__ import annotations  # 类型注解
from rag.evidence import INSUFFICIENT_ANSWER  # 原文为空时的固定拒答
from rag.structured.extract import extract_factors  # 从用户话里补因子
from rag.structured.records import merge_factors  # 合并时不擦掉旧值
from rag.structured.schema import factors_for_suffix  # 按优先级找缺口
from billing.turn_helper import empty_turn, merge_message  # 累加器
from domain.usage import TurnUsage  # 类型


# 这些核心字段没填时，先追问，不把整库塞进提示词
# 第一期只卡最关键的两个，避免每轮都盘问
REQUIRED_KEYS = ("topic", "subject")


def missing_questions(factors: dict[str, str], suffix: str = "") -> list[str]:
    """按 priority 返回还没填的因子对应的问句。"""
    pending = []  # (priority, question)
    for item in factors_for_suffix(suffix):  # schema 顺序里再按 priority 排序
        if item.key not in REQUIRED_KEYS:  # 第一期只追问必需字段
            continue
        if not str(factors.get(item.key, "")).strip():  # 空才算缺
            pending.append((item.priority, item.question))
    pending.sort(key=lambda pair: pair[0])  # 优先级小的先问
    return [question for _, question in pending]  # 只要问句


def run_consult(
    *,
    llm,
    user_message: str,
    factors: dict[str, str],
    records: list[dict],
    retrieve_context,  # 可调用对象：传入问题字符串，返回参考资料字符串
) -> tuple[str, dict[str, str],TurnUsage]:
    """跑一轮咨询。返回 (给用户的话, 更新后的因子, 用量)。"""
    turn = empty_turn()
    # 用户这句话本身也可能含有主题、对象，先抽一次再合并
    found = extract_factors(llm, user_message, suffix="")  # 对话侧只用核心因子
    updated = merge_factors(factors, found)  # 非空才覆盖
    gaps = missing_questions(updated, suffix="")  # 还缺什么
    if gaps:  # 关键因子不齐，本轮只问第一句
        answer = "为了检索得更准，请先补充这一点：\n" + gaps[0]
        return answer, updated,turn # 不调用向量库，用量为空

    # 因子齐了：结构化记录 + 混合检索原文 一起当上下文
    record_lines = []  # 每条因子记录压成一行，避免提示词过长
    for item in records[:8]:  # 最多带 8 条，防止把 SDM 全塞进去
        src = item.get("source", "")  # 来源路径
        fac = item.get("factors") or {}  # 该文件抽到的因子
        record_lines.append(f"来源: {src}\n因子: {fac}")
    record_block = "\n\n".join(record_lines) or "（暂无结构化因子记录，请先构建知识库）"
    try:
        context = retrieve_context(user_message)  # 复用现有 HybridRetriever
    except Exception:  # 检索失败不当成有资料
        context = ""

    if not (context or "").strip():  # 因子齐了，但没有足够原文
        return INSUFFICIENT_ANSWER, updated,turn # 不调用大模型编造结论，用量为空

    from langchain_core.messages import HumanMessage, SystemMessage

    system = (
        "你是基于知识库的助手。只能根据「结构化因子」和「原文片段」回答。\n"
        "资料不够就说明无法确定，不要编造。回答简洁，并提到来源文件名。"
    )
    human = (
        f"用户已确认的因子：{updated}\n\n"
        f"库内因子记录：\n{record_block}\n\n"
        f"原文片段：\n{context}\n\n"
        f"用户问题：{user_message}"
    )
    result = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    model_str = str(getattr(llm,"model_name",None) or "")
    turn = merge_message(turn,result,model=model_str)
    content = getattr(result, "content", result)  # 取出文本
    if not isinstance(content, str):
        content = str(content)
    return content.strip(), updated,turn # 用量在merge_message里累计了