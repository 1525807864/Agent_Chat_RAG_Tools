"""
抽不到就留空，禁止编造。
"""
from __future__ import annotations 
import json 
import re 
from rag.structured.schema import FactorDef,factors_for_suffix #因子定义

def _strip_fence(text:str)->str:
    """模型经常用 ```json...``` 等 fence 符号包文本，需要去掉"""
    raw = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.S)  # 围栏不一定在开头
    if match:
        return match.group(1).strip()
    return raw  #没有围栏就原样返回

def _factor_prompt(factors:list[FactorDef])->str:
    """生成因子抽取提示词。"""
    lines = []
    for item in factors:
        lines.append(f"- {item.key} ({item.kind}): {item.question}")  # key + 类型 + 含义
    return "\n".join(lines)


def extract_factors(llm,text:str,suffix)->dict[str,str]:
    """调用llm，返回{因子名：字符串值}返回抽取因子值。"""
    factors = factors_for_suffix(suffix) #按后缀添加
    allowed = {f.key for f in factors} #允许的因子名
    blank = {f.key: "" for f in factors} #默认空值 
    body = (text or "").strip() #待抽取正文
    if not body:
        return blank 
    
    #截断，避免一次把整本pdf塞进提示词，建库侧会按文件截断 
    clipped = body[:6000] #最多6000字
    system = (
        "你是信息抽取器。只根据给定文本填写 JSON 对象。\n"
        "规则：文本里没有的信息必须填空字符串；不要编造；不要解释；只输出 JSON。"
    )
    human = (
        "请抽取这些字段：\n"
        f"{_factor_prompt(factors)}\n\n"
        "文本：\n"
        f"{clipped}"
    )
    try:
        from langchain_core.messages import HumanMessage,SystemMessage
        result = llm.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=human),
            ]
        )
        content = getattr(result,"content",result) #有的返回对象，有的直接返回字符串
        if not isinstance(content,str):
            content = str(content)
        parsed = json.loads(_strip_fence(content)) #去掉围栏，反序列化
    except Exception:
        return blank 
    
    if not isinstance(parsed,dict):
        return blank 
    
    out = dict(blank) #默认控制，保证键安全
    for key in allowed:
        value = parsed.get(key,"")
        if value is None:
            value = ""
        if isinstance(value,bool): #true/false 收成字符串
            value = "true" if value else "false"
        out[key] = str(value).strip() #去掉空白
    return out 