"""
稠密向量+bm25稀疏，用rff融合结果
落盘：每个租户一份json[向量库+稀疏索引]，重启可加载
"""
from __future__ import annotations  # 现代类型注解
from collections import defaultdict  # 缺省 dict，累加 RRF 分
from dataclasses import dataclass  # 简单结果结构
from typing import Optional  # 可选
from langchain_core.documents import Document  # 文档类型
from rag.sparse_bm25 import BM25SparseIndex  # 稀疏索引
from rag.vector_store import VectorStoreManager  # 稠密向量管理器

@dataclass 
class HybridHit:
    """混合命中"""
    doc:Document 
    rrf_score: float 
    dense_rank: Optional[int] = None 
    sparse_rank: Optional[int] = None 

def _doc_key(doc:Document)->str:
    """用[来源+正文前缀]当去重键(chunk无稳定id时的折中)"""
    src = str((doc.metadata or {}).get("source", ""))  # file path
    body = (doc.page_content or "")[:120]  # 正文前120字当唯一标识
    return f"{src}:{body}"

def reciprocal_rank_fusion(
    ranked_lists: list[list[Document]],
    *,
    rrf_k:int=60,
)->list[HybridHit]:
    """对多路排序列表做 RRF 融合。
    ranked_lists[i][0] 是该路第 1 名。
    """
    scores: dict[str,float] = defaultdict(float) #key->累计RRF
    best_doc: dict[str,Document] = {}
    dense_rank: dict[str,int] = {}
    sparse_rank: dict[str,int] = {}
    for list_i,docs in enumerate(ranked_lists): #遍历每一路
        for rank,doc in enumerate(docs,start=1): #遍历该路每篇
            key = _doc_key(doc) #唯一标识
            scores[key] += 1.0 / (rrf_k+rank) #RRF公式
            best_doc[key] = doc #更新最佳
            if list_i == 0: 
                dense_rank[key] = rank 
            elif list_i == 1:
                sparse_rank[key] = rank 
    #按融合分排序
    ordered = sorted(scores.items(),key=lambda kv:kv[1],reverse=True)
    hits: list[HybridHit] = [] #输出
    for key,score in ordered:
        hits.append(
            HybridHit(
                doc=best_doc[key], #文档
                rrf_score=score, #RRF分数
                dense_rank=dense_rank.get(key), #稠密排名
                sparse_rank=sparse_rank.get(key), #稀疏排名
            )
        )
    return hits 

class HybridRetriever:
    """对外统一：retrieve(query)->返回list[HybridHit]"""
    def __init__(
        self,
        vector_store: VectorStoreManager,  # 稠密
        sparse_index: BM25SparseIndex,  # 稀疏
        *,
        top_k: int = 5,  # 最终返回条数
        fetch_k: int = 10,  # 每一路先取多少再融合
        rrf_k: int = 60,  # RRF 平滑常数，常用 60
        mode: str = "hybrid",  # dense | sparse | hybrid
    ) -> None:
        self.vector_store = vector_store 
        self.sparse_index = sparse_index 
        self.top_k = top_k 
        self.fetch_k = fetch_k 
        self.rrf_k = rrf_k 
        self.mode = mode 

    def retrieve(self, query: str) -> list[HybridHit]:
        """按 mode 检索并（必要时）融合。"""
        mode = (self.mode or "hybrid").lower()  # 规范化
        dense_docs: list[Document] = []  # 稠密结果
        sparse_docs: list[Document] = []  # 稀疏结果（只要 Document）
        if mode in {"dense", "hybrid", "semantic"}:  # 需要稠密
            try:
                dense_docs = self.vector_store.similarity_search(
                    query, k=self.fetch_k  # 多取一点给融合
                )
            except Exception:
                dense_docs = []  # 向量失败时降级，不拖垮整次问答
        if mode in {"sparse", "hybrid", "keyword"}:  # 需要稀疏
            pairs = self.sparse_index.search(query, k=self.fetch_k)  # (doc, score)
            sparse_docs = [d for d, _ in pairs]  # 只留文档，分数交给 RRF
        if mode in {"dense", "semantic"}:  # 只稠密
            return [
                HybridHit(doc=d, rrf_score=1.0 / (self.rrf_k + i), dense_rank=i)
                for i, d in enumerate(dense_docs[: self.top_k], start=1)
            ]
        if mode in {"sparse", "keyword"}:  # 只稀疏
            return [
                HybridHit(doc=d, rrf_score=1.0 / (self.rrf_k + i), sparse_rank=i)
                for i, d in enumerate(sparse_docs[: self.top_k], start=1)
            ]
        # 默认 hybrid：两路 RRF
        fused = reciprocal_rank_fusion(
            [dense_docs, sparse_docs],  # 顺序：0=dense, 1=sparse
            rrf_k=self.rrf_k,
        )
        return fused[: self.top_k]  # 截断到 top_k
