"""应用层安全策略：内容过滤 + 速率限制统一入口。

原先仅部分 ask_* 接入过滤器；商业场景要求所有对外问答路径经过本策略。
"""

from __future__ import annotations

from typing import Optional

from shared.errors import AppError, ErrorCode
from safety.content_filter import ContentFilter
from safety.rate_limiter import AsyncRateLimiter


class SecurityPolicy:
    """用例层安全门禁。

    - ``check_input``：同步内容过滤（关键词 / 注入 / 长度）
    - ``acquire``：异步速率限制（滑动窗口）
    - ``guard``：组合二者；失败抛 ``AppError`` 或返回拦截文案（由 ``raise_on_block`` 控制）
    """

    def __init__(
        self,
        content_filter: ContentFilter,
        rate_limiter: AsyncRateLimiter,
    ) -> None:
        self.content_filter = content_filter
        self.rate_limiter = rate_limiter

    def check_input(self, text: str, *, raise_on_block: bool = False) -> tuple[bool, str]:
        sanitized = self.content_filter.sanitize_input(text)
        passed, reason = self.content_filter.check_input(sanitized)
        if not passed and raise_on_block:
            raise AppError(
                ErrorCode.CONTENT_BLOCKED,
                reason or "内容被安全策略拦截",
                http_status=400,
            )
        return passed, reason

    async def acquire_rate_limit(self, *, raise_on_limit: bool = False) -> bool:
        ok = await self.rate_limiter.acquire()
        if not ok and raise_on_limit:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "请求过于频繁, 请稍后再试",
                http_status=429,
            )
        return ok

    async def guard(
        self,
        text: str,
        *,
        rate_limit: bool = True,
        as_text: bool = True,
    ) -> Optional[str]:
        """执行安全检查。

        Returns
        -------
        None
            通过。
        str
            ``as_text=True`` 时返回可直接给用户的拦截说明；否则抛 ``AppError``。
        """
        passed, reason = self.check_input(text, raise_on_block=not as_text)
        if not passed:
            return f"[安全拦截] {reason}"

        if rate_limit:
            ok = await self.acquire_rate_limit(raise_on_limit=not as_text)
            if not ok:
                return "请求过于频繁, 请稍后再试"
        return None
