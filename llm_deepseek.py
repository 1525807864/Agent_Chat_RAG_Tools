"""兼容层：转发到 ``infrastructure.llm.deepseek``。

历史 ``DeepSeekLLM`` / ``DeepSeekChatLLM`` 已移除；请使用 ``DeepSeekChatModel``。
示例见 ``examples/legacy_chat_demo.py``。
"""

from infrastructure.llm.deepseek import DeepSeekChatModel, _convert_message_to_dict

__all__ = ["DeepSeekChatModel", "_convert_message_to_dict"]
