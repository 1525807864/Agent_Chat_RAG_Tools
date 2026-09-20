# E2E：Playwright MCP 接入 + URL 校验。不自研 browser click/fill。

from e2e.mcp_playwright import e2e_system_hint, playwright_mcp_session
from e2e.url_guard import E2EUrlError, start_path_from_url, validate_base_url

__all__ = [
    "playwright_mcp_session",
    "e2e_system_hint",
    "validate_base_url",
    "start_path_from_url",
    "E2EUrlError",
]
