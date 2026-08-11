"""内容安全过滤器

知识点:
1. 多层过滤: 输入过滤 + 输出过滤 + 越狱检测
2. 关键词过滤容易被绕过 (同音字、拆分) → 语义级检测需专业审核模型
3. 零宽字符清理: 防止绕过关键词检测
"""

import re


class ContentFilter:
    """内容安全过滤器"""

    def __init__(self, blocked_keywords: list[str] | None = None):
        self.blocked_keywords = blocked_keywords or []
        self._compiled_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in self.blocked_keywords
        ]

    def add_blocked_keyword(self, keyword: str) -> None:
        self.blocked_keywords.append(keyword)
        self._compiled_patterns.append(re.compile(re.escape(keyword), re.IGNORECASE))

    def check_input(self, text: str) -> tuple[bool, str]:
        """检查用户输入, 返回 (是否通过, 拒绝原因)"""
        if not text or not text.strip():
            return False, "输入不能为空"

        if len(text) > 10000:
            return False, f"输入过长 ({len(text)} 字符, 最大允许 10000)"

        for pattern in self._compiled_patterns:
            if pattern.search(text):
                return False, "输入包含不合规内容"

        # Prompt Injection 检测
        jailbreak_patterns = [
            r"(?i)(ignore|forget|disregard).*(previous|above|all).*(instruction|prompt|rule)",
            r"(?i)(you are now|you're now|act as).*(DAN|jailbreak|evil|unethical)",
            r"(?i)(pretend|imagine|扮演).*(没有规则|no rule|without rule)",
        ]
        for pattern in jailbreak_patterns:
            if re.search(pattern, text):
                return False, "检测到潜在的 prompt injection 攻击"

        return True, ""

    def check_output(self, text: str) -> tuple[bool, str]:
        """检查 LLM 输出"""
        if len(text) > 50000:
            return False, "输出过长"

        for pattern in self._compiled_patterns:
            if pattern.search(text):
                return False, "输出包含不合规内容"

        return True, ""

    def sanitize_input(self, text: str) -> str:
        """净化输入 — 去除零宽字符, 规范化空白"""
        text = re.sub(r'[​‌‍‎‏﻿]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
