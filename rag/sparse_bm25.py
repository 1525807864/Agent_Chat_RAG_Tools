#spare_bm25.py 稀疏检索[bm25]索引
"""
作用：补稠密向量对[专用名词/编号/精确词]不敏感的短板
落盘：每个租户一份json[文档原文+token],重启可加载
"""
from __future__ import annotations #允许类型注解里用list[str] 现代写法
import json 
import re 
from pathlib import Path 
from langchain_core.documents import Document #与向量侧统一的文档结构

def tokenize(text:str)->list[str]:
    """
    极简分词：英文按词，中文按单字
    """
    text = (text or "").lower()  # 英文统一小写，提高命中
    #抓连续字母数字，或单个CJK汉字
    parts = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]",text)
    return [p for p in parts if p] #过滤空串

class BM25SparseIndex:
    """租户级bm25索引：build->save->load->search"""
    def __init__(self)->None:
        self._docs: list[Document] = []#与向量库对齐的document列表
        self._corpus_tokens: list[list[str]] = []#每篇文档的token列表
        self._bm25 = None #rank_bm25.BM25Okapi实例 未build时为None 

    @property
    def size(self)->int:
        """当前索引有多少条chunk"""
        return len(self._docs)

    def build(self,docs:list[Document])->int:
        """用一批Document重建索引（全量覆盖）"""
        from rank_bm25 import BM25Okapi  # 延迟导入，没装依赖时只在 build 才报错

        self._docs = list(docs) #拷贝一份，避免外部改List影响索引
        self._corpus_tokens = [tokenize(d.page_content) for d in self._docs] #逐篇分词
        #空语料时 BM25Okapi 可能异常，给一个空壳语料
        if not self._corpus_tokens:
            self._corpus_tokens = [[]]  # 占位，避免构造失败
            self._docs = []  # 真正可检索文档仍为空
            self._bm25 = BM25Okapi([["__empty__"]])  # 最小合法语料
            return 0  # 告诉调用方建了 0 条
        self._bm25 = BM25Okapi(self._corpus_tokens) #训练IDF / 平均文档长度
        return len(self._docs) #返回实际建成多少条 
    
    def search(self,query:str,k:int=5)->list[tuple[Document,float]]:
        """bm25检索，返回(document,score)列表，按分数降序"""
        if self._bm25 is None or not self._docs: #未建库或空库
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return [] #无结果
        scores = self._bm25.get_scores(q_tokens) #对语料每篇打分，长度=文档数量
        # 小语料 IDF≈0 时，用查询词命中数做微弱加成，保证精确词能排到前面
        q_set = set(q_tokens)
        boosted = []
        for i, base in enumerate(scores):
            overlap = len(q_set.intersection(self._corpus_tokens[i]))
            boosted.append(float(base) + 0.01 * overlap)
        ranked = sorted(range(len(self._docs)), key=lambda i: boosted[i], reverse=True)
        out: list[tuple[Document, float]] = []
        for i in ranked[: max(k, 0)]:
            out.append((self._docs[i], boosted[i]))
        return out 
    
    def save(self,path:str|Path)->None:
        """把原文与metadata落到json,下次load再build（简单可靠）"""
        path = Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        payload = {
            "docs":[
                {
                    "page_content":d.page_content,#正文
                    "metadata":dict(d.metadata or {}),
                }
                for d in self._docs
            ]
        }
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    
    @classmethod 
    def load(cls,path:str|Path)->"BM25SparseIndex":
        """从json加载并重建bm25:文件不存在则返回空索引"""
        path = Path(path)
        idx = cls() #新实例
        if not path.exists():
            return idx  #空索引，search[]
        raw = json.loads(path.read_text(encoding="utf-8"))
        docs = [  # 还原 Document
            Document(
                page_content=item.get("page_content") or "",
                metadata=item.get("metadata") or {},
            )
            for item in (raw.get("docs") or [])
        ]
        idx.build(docs) #重建索引
        return idx 
    
    def __repr__(self)->str:
        """好看的字符串表示"""
        return f"<BM25SparseIndex[{self.size}]>"
    
    def __str__(self)->str:
        """友好文本输出"""
        return f"BM25SparseIndex[{self.size}]"
        
