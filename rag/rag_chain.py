"""RAG / GraphRAG 问答链（LCEL）。

标准 RAG：向量检索 → format_docs → Prompt → LLM
GraphRAG：GraphRAGRetriever.retrieve → merged_context → 同一 Prompt

空检索结果会注入明确提示语，降低幻觉。
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from rag.knowledge_graph import GraphRAGRetriever

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个基于知识库的问答助手。请根据以下参考资料回答问题。

规则:
1. 如果参考资料中有答案, 基于资料回答, 并标注来源
2. 如果资料不足以回答, 明确说明"根据现有资料无法确定"
3. 不要编造资料中没有的信息
4. 回答要简洁、准确
5. 若资料提示未找到文档或图谱为空, 如实告知用户需要先构建知识库

参考资料:
{context}"""),
    ("human", "{question}"),
])


def format_docs(docs: list[Document]) -> str:
    """把检索到的 Document 列表格式化为 Prompt 的 context。"""
    if not docs:
        return "（未找到相关资料）"
    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "未知来源")
        parts.append(f"[来源{i}: {source}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def create_rag_chain(llm, retriever):
    """创建标准 RAG 链。

    用法::

        chain = create_rag_chain(llm, retriever)
        answer = chain.invoke({"question": "什么是RAG?"})
    """
    chain = (
        {
            "context": RunnableLambda(
                lambda x: format_docs(retriever.invoke(x["question"]))
            ),
            "question": RunnablePassthrough(),
        }
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )
    return chain


def create_graph_rag_chain(llm, graph_rag_retriever, *, top_k: int | None = None):
    """创建 GraphRAG 链 — 向量检索 + 知识图谱邻域合并后问答。

    ``graph_rag_retriever`` 需实现 ``retrieve(query) -> dict``，且含 ``merged_context``。
    图谱为空时仍可退化到向量侧；两侧皆空则 context 为明确空结果提示。
    """

    def _retrieve(query: str) -> str:
        kwargs = {}
        if top_k is not None:
            kwargs["top_k"] = top_k
        result = graph_rag_retriever.retrieve(query, **kwargs)
        ctx = result.get("merged_context")
        if not ctx:
            return GraphRAGRetriever.EMPTY_CONTEXT_HINT
        return ctx

    chain = (
        # 从问题中取出merged_context字符串，填进prompt的context
        {
            "context": RunnableLambda(lambda x: _retrieve(x["question"])),
            "question": RunnablePassthrough(),
        }
        | RAG_PROMPT
        | llm
    )
    return chain
