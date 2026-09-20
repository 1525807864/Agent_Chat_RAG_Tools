# ============================================================================
# query_router.py — 轻量查询路由
# 输出策略名，交给 HybridRetriever.mode；以后可换成 LLM 分类器
# 预留：summary -> RAPTOR；multi_hop -> GraphRAG
# ============================================================================

from __future__ import annotations  # 类型注解

import re  # 正则匹配问句特征
from dataclasses import dataclass  # 路由结果


@dataclass
class RouteDecision:
    """路由器输出：给检索层看的策略 + 人类可读原因。"""

    strategy: str  # hybrid | keyword | semantic | multi_hop | summary
    reason: str  # 调试 / 打进 trace


# 偏「精确词 / 编号」的模式
_KEYWORD_HINTS = re.compile(
    r"(\b[A-Z]{2,}[-_]?\d+\b)|"  # 如 API-12、ABC123
    r"(编号|代号|错误码|报错|报错码|版本号)|"  # 中文精确意图
    r"(\b\d{4,}\b)"  # 较长数字串
)

# 偏「多跳 / 关系」——以后走 GraphRAG
_MULTI_HOP_HINTS = re.compile(
    r"(关系|关联|导致|依赖|调用链|上下游|谁.*负责|如何影响)"
)

# 偏「概括 / 总览」——以后走 RAPTOR
_SUMMARY_HINTS = re.compile(
    r"(总结|概括|综述|整体|概览|主要讲了什么|全文)"
)


def route_query(question: str) -> RouteDecision:
    """根据问句浅层特征选策略；拿不准就 hybrid。"""
    q = (question or "").strip()  # 去空白
    if not q:  # 空问题
        return RouteDecision("hybrid", "空查询，默认 hybrid")  # 兜底

    if _SUMMARY_HINTS.search(q):  # 概括类
        # 第一期还没有 RAPTOR：先退回 semantic（稠密更适合段落语义）
        return RouteDecision("semantic", "命中概括类关键词，暂用 semantic；二期可换 RAPTOR")

    if _MULTI_HOP_HINTS.search(q):  # 关系类
        # 第一期仍走 hybrid；ask_graph_rag 仍可由用户选手动 mode
        return RouteDecision("hybrid", "命中多跳/关系词，一期仍 hybrid；二期可换 GraphRAG")

    if _KEYWORD_HINTS.search(q):  # 精确词
        return RouteDecision("keyword", "命中编号/错误码等，偏 BM25")

    # 默认：两路融合最稳
    return RouteDecision("hybrid", "无特殊信号，默认 dense+BM25 RRF")