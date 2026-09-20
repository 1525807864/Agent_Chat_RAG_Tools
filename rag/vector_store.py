"""向量数据库封装 — 支持 ChromaDB / FAISS

知识点:
1. Embedding: 文本 → 高维向量, 语义相近的文本向量距离近
2. ChromaDB vs FAISS:
   - ChromaDB: 自带持久化, 元数据过滤, 适合生产
   - FAISS: Meta 出品, 纯内存, 速度极快, 适合本地实验
3. MMR (Maximum Marginal Relevance): 避免检索到重复内容, lambda 控制多样性
"""

import os
from typing import Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


class VectorStoreManager:
    """向量存储管理器 — 懒加载 + 统一接口"""

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        persist_dir: str = "data/vector_store",
        backend: str = "chromadb",
    ):
        self.embedding_model_name = embedding_model
        self.persist_dir = persist_dir
        self.backend = backend
        self._embedding: Optional[Embeddings] = None
        self._store = None

    @property
    def embeddings(self) -> Embeddings:
        if self._embedding is None:
            from infrastructure.embeddings.factory import create_embeddings
            self._embedding = create_embeddings()
        return self._embedding

    def get_or_create_store(self):
        if self._store is not None:
            return self._store

        if self.backend == "chromadb":
            from langchain_chroma import Chroma
            os.makedirs(self.persist_dir, exist_ok=True)
            self._store = Chroma(
                embedding_function=self.embeddings,
                persist_directory=self.persist_dir,
            )
        elif self.backend == "faiss":
            from langchain_community.vectorstores import FAISS
            self._store = FAISS(embedding_function=self.embeddings)
        else:
            raise ValueError(f"不支持的向量存储后端: {self.backend}")

        return self._store

    def add_documents(self, docs: list[Document],batch_size:int=10) -> int:
        store = self.get_or_create_store()
        if not docs:
            return 0 
        size = max(1,min(batch_size,64))
        for i in range(0,len(docs),size):
            store.add_documents(docs[i:i+size])
        return len(docs)

    def similarity_search(
        self, query: str, k: int = 5, filter: Optional[dict] = None
    ) -> list[Document]:
        store = self.get_or_create_store()
        return store.similarity_search(query, k=k, filter=filter)

    def mmr_search(
        self, query: str, k: int = 5, fetch_k: int = 20, lambda_mult: float = 0.5
    ) -> list[Document]:
        """MMR 检索 — 在相关性 (lambda=1.0) 和多样性 (lambda=0.0) 之间平衡"""
        store = self.get_or_create_store()
        return store.max_marginal_relevance_search(
            query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult
        )

    def delete_by_source(self, source: str) -> int:
        store = self.get_or_create_store()
        if self.backend == "chromadb":
            from langchain_chroma import Chroma
            if isinstance(store, Chroma):
                collection = store._collection
                results = collection.get(where={"source": source})
                ids = results.get("ids", [])
                if ids:
                    collection.delete(ids=ids)
                return len(ids)
        return 0
