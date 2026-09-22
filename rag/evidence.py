#evidence.py - 判断这次检索能不能支撑回答
#没有非空正文时，不要把问题交给大模型自由发挥

from __future__ import annotations  # 使用 list[Document] 这种写法
from langchain_core.documents import Document  # 和向量库同一套文档类型

#固定文案，测试和界面都是一样，以中文为主
INSUFFICIENT_ANSWER = "根据现有资料无法确定。知识库里没有足够相关的原文，请换一种问法或先检查文档是否已成功建库。"

def has_enough_evidence(docs:list[Document])->bool:
    """判断这次检索能不能支撑回答""" 
    """至少有一条切块带非空正文，才允许生成回答"""
    for doc in docs:
        text = (getattr(doc,"page_content","") or "").strip() #有的返回对象，有的直接返回字符串
        if text:
            return True 
    return False  #空列表或者全是空白都不够