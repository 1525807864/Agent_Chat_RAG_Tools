"""把本轮打开的文件拼进任务前缀，减少 Agent / Chat 先读盘的往返。"""

from __future__ import annotations


def build_files_prefix(files: list | None) -> str:
    if not files:
        return ""
    chunks: list[str] = []
    for f in files:
        path = getattr(f, "path", None) or (
            f.get("path") if isinstance(f, dict) else ""
        )
        content = getattr(f, "content", None) or (
            f.get("content") if isinstance(f, dict) else ""
        )
        if not path:
            continue
        text = content if isinstance(content, str) else str(content)
        if len(text) > 6000:
            text = text[:6000] + f"\n... 已截断，原 {len(content)} 字符"
        chunks.append(f"### FILE: {path}\n```\n{text}\n```")
    if not chunks:
        return ""
    return "以下是用户工作区中已打开的文件：\n\n" + "\n\n".join(chunks) + "\n\n"
