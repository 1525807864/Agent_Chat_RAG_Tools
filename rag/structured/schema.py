"""
核心因子：所有文档都抽
扩展因子：按文件类型追加
priority越小越先问用户
"""
from __future__ import annotations 
from dataclasses import dataclass
@dataclass(frozen=True)
class FactorDef:
    """一个因子的定义，不是某篇文档抽出来的值"""
    key: str
    question: str 
    kind: str 
    priority: int 

#所有文档都尝试抽取的字段
CORE_FACTORS: list[FactorDef] = [
    FactorDef("topic", "这份材料主要在讲什么主题？", "text", 1),
    FactorDef("subject", "它涉及的对象、系统或功能是什么？", "text", 2),
    FactorDef("key_terms", "有哪些必须原样匹配的关键术语或编号？", "text", 3),
    FactorDef("condition", "在什么前提或条件下这些内容才适用？", "text", 4),
    FactorDef("outcome", "材料给出的结论、步骤或结果是什么？", "text", 5),
]
#按后缀追加。键是小写后缀，值是额外因子
EXTENSION_FACTORS: dict[str,list[FactorDef]] = {
    ".pdf": [
            FactorDef("section", "你关心的是文档的哪一章或哪一节？", "text", 2),
    ],
    ".xlsx": [
        FactorDef("sheet_topic", "你要查的是表里的哪一类记录？", "text", 2),
    ],
    ".md": [
        FactorDef("page_or_flow", "你要操作的是哪个页面或哪一步流程？", "text", 2),
    ],
}
def factors_for_suffix(suffix:str)->list[FactorDef]:
    extra = EXTENSION_FACTORS.get((suffix or "").lower(), [])  # 未知后缀就只有核心因子
    return list(CORE_FACTORS) + list(extra)  # 拷贝一份，避免调用方改到全局列表

def empty_factor_dict(suffix: str) -> dict[str, str]:
    """建一份全空的因子字典，键来自 schema，值先用空字符串。"""
    return {item.key: "" for item in factors_for_suffix(suffix)}  # 空字符串表示还没填