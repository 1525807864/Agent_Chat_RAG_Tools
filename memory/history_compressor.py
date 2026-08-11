"""
历史消息摘要压缩器
 知识点:
  1. ConversationSummaryBufferMemory 原理:
     - 保留最近 N 条完整消息
     - 超过窗口的消息用 LLM 生成摘要
     - 摘要 + 最近消息 = 完整上下文

  2. Token 计数: tiktoken 精确计算, 防止超出模型上下文窗口

  3. 边界考虑:
     - 摘要本身也占 token, 需要控制摘要长度
     - 压缩触发条件: 消息数 > window_size 或 总 token 数 >max_tokens

"""
import tiktoken
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
class HistoryCompressor:
    """对话历史压缩器 — 用 LLM 摘要「窗口外」旧消息，控制上下文长度。

    已在 ``AgentApplication.ask_chat`` 中接入：当消息数/Token 超阈值时，
    对窗口外旧消息做 LLM 摘要，摘要注入 system，最近窗口仍进 history。
    """

    def __init__(
            self,
            llm: BaseChatModel,
            window_size: int = 10,  # 保留最近 N 条完整消息不做摘要
            max_summary_tokens: int = 200,
            encoding_name: str = "cl100k_base",
    ):
        self.llm = llm
        self.window_size = window_size
        self.max_summary_tokens = max_summary_tokens
        try:
            self.encoder = tiktoken.get_encoding(encoding_name)
        except Exception:
            self.encoder = tiktoken.get_encoding("cl100k_base")
    def count_tokens(self,messages:list[dict])->int:
        """计算消息列表的总token数"""
        total = 0
        for msg in messages:
            total += len(self.encoder.encode(msg.get("content","")))
        return total
    def should_compress(self,messages:list[dict],max_context_tokens:int = 6000)->bool:
        """判断是否需要压缩"""
        if len(messages) < self.window_size or self.count_tokens(messages) < max_context_tokens:
            return False
        return True
    async def compress(self,messages: list[dict],existing_summmary: str="")->tuple[list[dict],str]:
        """
        压缩历史消息
        Args:
            messages:完整消息列表
            existing_summmary: 已存在的摘要(累计压缩)
        Returns:
            (保留的最近的消息，更新后的摘要文本)
        """
        if len(messages) <= self.window_size:
            return messages,existing_summmary
        #分割:[需要摘要的旧消息] + [保留的最近消息]
        old_messages = messages[:-self.window_size]
        recent_messages = messages[-self.window_size:]
        # 用llm生成摘要
        summary_prompt = self._build_summary_prompt(old_messages,existing_summmary)

        try:
            from langchain_core.messages import HumanMessage
            new_summary = self.llm.invoke([HumanMessage(content=summary_prompt)]).content
            #裁剪摘要的长度
            new_summary = self._trim_summary(new_summary)
        except Exception:
            new_summary = existing_summmary#摘要裁剪失败时保留旧摘要
        return recent_messages,new_summary
    def _build_summary_prompt(self,old_messages:list[dict],existing_summary:str)->str:
        """构建摘要prompt"""
        dialog_text = "\n".join(
            f"{msg['role']}:{msg['content']}" for msg in old_messages
        )
        base = f"""
        请将以下对话历史压缩为一段简要的摘要（不超过:{self.max_summary_tokens}字）：已有摘要:{existing_summary or '无'}
        对话历史:{dialog_text}
        要求：提取关键信息、决策、用户偏好、忽略寒暄和重复内容。
        """
        return base
    #裁剪摘要，确保不超过最大token数
    def _trim_summary(self,new_summary:str)->str:
        tokens = self.encoder.encode(new_summary)
        if len(tokens) > self.max_summary_tokens:
            tokens = tokens[:self.max_summary_tokens]
            return self.encoder.decode(tokens)+"..."
        return new_summary

def format_message_for_prompt(messages: list[dict], summary: str = "") -> str:
    parts: list[str] = []
    if summary:
        parts.append("【对话历史摘要】")
        parts.append(summary)
        parts.append("")
        parts.append("--- 以下是当前对话 ---")
        parts.append("")
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role","user")
        content = msg.get("content","")
        #向后合并同一角色的连续消息
        j = i+1
        while j < len(messages) and messages[j].get("role") == role:
            content += "\n"+messages[j].get("content","")
            j+=1
        parts.append(f"{role}:{content}")
        i = j
    return "\n".join(parts)
