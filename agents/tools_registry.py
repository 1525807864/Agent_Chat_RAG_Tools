"""工具注册与管理（含路径沙箱与代码执行收紧）。

安全边界
========
- ``read_file``：仅允许读取 ``allowed_roots``（默认项目 ``data/``）下的文件
- ``execute_python``：禁用 import / open / eval / exec 嵌套；限制危险内置
- ``calculator``：仍用受限 eval（无 builtins）

``create_default_registry(allowed_roots=..., project_root=...)`` 由应用层注入配置。
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import httpx
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from config.settings import get_settings
from shared.path_security import PathSecurityError, get_project_root, resolve_safe_path


# ============ 内置工具定义 ============

class CalculatorInput(BaseModel):
    expression: str = Field(description="数学表达式, 如 '2 + 3 * 4'")


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")


@tool(args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """执行数学计算"""
    try:
        # 极简白名单：禁止名称查找，仅允许字面量与运算符
        result = eval(expression, {"__builtins__": {}}, {})
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算出错: {e}"


@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """使用 Tavily 搜索网页，返回标题、链接与摘要，供回答事实类问题。"""
    settings = get_settings()
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        return "搜索失败：未配置 TAVILY_API_KEY，请在 .env 中设置后重启后端。"

    q = (query or "").strip()
    if not q:
        return "搜索失败：关键词不能为空"

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": q,
        "max_results": settings.search_result_limit,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        # 部分环境证书链/杀软中间人会导致 UNEXPECTED_EOF；可用 SEARCH_SSL_VERIFY=false
        with httpx.Client(
            timeout=settings.search_timeout,
            verify=settings.search_ssl_verify,
        ) as client:
            resp = client.post(url, json=payload)
    except httpx.TimeoutException:
        return f"搜索超时（>{settings.search_timeout}s）：{q}"
    except httpx.HTTPError as e:
        hint = ""
        if "SSL" in str(e).upper() or "CERTIFICATE" in str(e).upper():
            hint = "（可在 .env 设置 SEARCH_SSL_VERIFY=false 后重试）"
        return f"搜索网络错误：{e}{hint}"

    if resp.status_code != 200:
        detail = resp.text[:500]
        return f"搜索失败 HTTP {resp.status_code}: {detail}"

    try:
        data = resp.json()
    except Exception as e:
        return f"搜索失败：解析响应失败: {e}"

    results = data.get("results") or []
    if not results:
        return f"未找到与「{q}」相关的网页"

    lines: list[str] = [f"搜索词: {q}", f"共 {len(results)} 条结果:", ""]
    for i, item in enumerate(results, 1):
        title = (item.get("title") or "（无标题）").strip()
        link = (item.get("url") or "").strip()
        snippet = (item.get("content") or item.get("snippet") or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        lines.append(f"{i}. {title}")
        if link:
            lines.append(f"   链接: {link}")
        if snippet:
            lines.append(f"   摘要: {snippet}")
        lines.append("")

    return "\n".join(lines).strip()


class FileReadInput(BaseModel):
    file_path: str = Field(description="文件路径（必须位于允许的数据目录内）")


def make_read_file_tool(
    allowed_roots: Sequence[str | Path],
    project_root: Path | None = None,
) -> BaseTool:
    """工厂：生成带路径白名单的 read_file 工具。"""

    roots = list(allowed_roots)
    base = project_root or get_project_root()

    @tool(args_schema=FileReadInput)
    def read_file(file_path: str) -> str:
        """读取允许目录内的文件内容（路径沙箱）。"""
        try:
            path = resolve_safe_path(
                file_path,
                allowed_roots=roots,
                project_root=base,
                must_exist=True,
                expect_dir=False,
            )
            content = path.read_text(encoding="utf-8")
            if len(content) > 5000:
                return content[:5000] + f"\n... (文件过长, 已截断, 原{len(content)}字符)"
            return content
        except PathSecurityError as e:
            return f"读取文件被拒绝: {e}"
        except Exception as e:
            return f"读取文件失败: {e}"

    return read_file


class CodeExecuteInput(BaseModel):
    code: str = Field(description="要执行的 Python 代码")
    timeout: int = Field(default=5, description="超时时间(秒)（当前为协作式限制提示）")


_FORBIDDEN_CODE_PATTERNS = (
    "import ",
    "from ",
    "__",
    "open(",
    "exec(",
    "eval(",
    "compile(",
    "globals(",
    "locals(",
    "getattr(",
    "setattr(",
    "delattr(",
    "breakpoint(",
    "os.",
    "sys.",
    "subprocess",
    "socket",
    "pathlib",
    "shutil",
)


@tool(args_schema=CodeExecuteInput)
def execute_python(code: str, timeout: int = 5) -> str:
    """执行 Python 代码（收紧沙箱）。

    禁止 import / 文件与网络访问；仅提供安全内置集合。
    生产环境仍应使用 Docker / gVisor 等进程级隔离。
    """
    lowered = code.lower()
    for pat in _FORBIDDEN_CODE_PATTERNS:
        if pat in lowered or pat in code:
            return f"代码执行被拒绝: 检测到不安全片段 ({pat.strip()})"

    if timeout > 30:
        return "代码执行被拒绝: timeout 不得超过 30 秒"

    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "filter": filter, "float": float, "int": int,
        "len": len, "list": list, "map": map, "max": max, "min": min,
        "range": range, "round": round, "set": set, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "zip": zip, "print": print,
        "True": True, "False": False, "None": None,
    }
    try:
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = buffer = StringIO()
        try:
            exec(  # noqa: S102 — 有意受限沙箱
                code,
                {"__builtins__": safe_builtins},
                {},
            )
        finally:
            sys.stdout = old_stdout
        output = buffer.getvalue()
        return output or "代码执行成功 (无输出)"
    except Exception as e:
        return f"代码执行错误: {e}"


# ============ 工具注册中心 ============

class ToolRegistry:
    """工具注册中心。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._tool_permissions: dict[str, set[str]] = {}

    def register(self, tool_obj: BaseTool) -> None:
        """按 tool.name 注册；同名覆盖。"""
        self._tools[tool_obj.name] = tool_obj

    def unregister(self, tool_name: str) -> None:
        self._tools.pop(tool_name, None)

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_tools_for_agent(self, agent_name: str) -> list[BaseTool]:
        """获取特定 Agent 可用的工具（最小权限原则）。"""
        allowed = self._tool_permissions.get(agent_name, set(self._tools.keys()))
        return [t for name, t in self._tools.items() if name in allowed]

    def grant_tool(self, agent_name: str, tool_name: str) -> None:
        if agent_name not in self._tool_permissions:
            self._tool_permissions[agent_name] = set()
        self._tool_permissions[agent_name].add(tool_name)

    def revoke_tool(self, agent_name: str, tool_name: str) -> None:
        if agent_name in self._tool_permissions:
            self._tool_permissions[agent_name].discard(tool_name)


class WsPathInput(BaseModel):
    path: str = Field(
        default=".",
        description="相对工作区根的路径；列目录可用 '.' 或子目录如 src",
    )


class WsWriteInput(BaseModel):
    path: str = Field(description="相对工作区根的文件路径，如 src/app.py")
    content: str = Field(description="要写入的完整文件内容（覆盖写）")


def make_workspace_tools(workspace_root: str | Path) -> list[BaseTool]:
    """为单轮请求绑定用户工作区根的 list / read / write 工具。"""
    root = Path(workspace_root).resolve()
    allowed = [root]

    @tool(args_schema=WsPathInput)
    def list_workspace_dir(path: str = ".") -> str:
        """列出工作区内某目录下一层的文件与子目录。"""
        try:
            rel = path.strip() or "."
            d = resolve_safe_path(
                rel,
                allowed_roots=allowed,
                project_root=root,
                must_exist=True,
                expect_dir=True,
            )
            items: list[str] = []
            for p in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if p.name.startswith("."):
                    continue
                kind = "dir" if p.is_dir() else "file"
                items.append(f"[{kind}] {p.relative_to(root).as_posix()}")
            return "\n".join(items) if items else "(空目录)"
        except PathSecurityError as e:
            return f"列出失败: {e}"
        except Exception as e:
            return f"列出失败: {e}"

    @tool(args_schema=WsPathInput)
    def read_workspace_file(path: str) -> str:
        """读取工作区内文本文件；修改代码前应先读取。"""
        try:
            fp = resolve_safe_path(
                path.strip(),
                allowed_roots=allowed,
                project_root=root,
                must_exist=True,
                expect_dir=False,
            )
            text = fp.read_text(encoding="utf-8")
            if len(text) > 8000:
                return text[:8000] + f"\n... 已截断，原 {len(text)} 字符"
            return text
        except Exception as e:
            return f"读取失败: {e}"

    @tool(args_schema=WsWriteInput)
    def write_workspace_file(path: str, content: str) -> str:
        """覆盖写入工作区内文件，用于按用户要求修改或生成代码。"""
        try:
            fp = resolve_safe_path(
                path.strip(),
                allowed_roots=allowed,
                project_root=root,
                must_exist=False,
                expect_dir=False,
            )
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return f"已写入: {Path(path).as_posix()} ({len(content)} 字符)"
        except Exception as e:
            return f"写入失败: {e}"

    return [list_workspace_dir, read_workspace_file, write_workspace_file]


def create_default_registry(
    allowed_roots: Sequence[str | Path] | None = None,
    project_root: Path | str | None = None,
    *,
    enable_execute_python: bool = False, #默认关闭
) -> ToolRegistry:
    """创建预注册常用工具的注册中心。

    Parameters
    ----------
    allowed_roots:
        ``read_file`` 白名单根；默认 ``["data"]``。
    project_root:
        解析相对路径的基准；默认仓库根。
    """
    roots = list(allowed_roots) if allowed_roots is not None else ["data"]
    base = Path(project_root).resolve() if project_root else get_project_root()
    # 确保工作区目录存在，便于演示写/读
    (base / "data" / "workspace").mkdir(parents=True, exist_ok=True)

    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(web_search)
    registry.register(make_read_file_tool(roots, project_root=base))
    if enable_execute_python:
        registry.register(execute_python)
    return registry
