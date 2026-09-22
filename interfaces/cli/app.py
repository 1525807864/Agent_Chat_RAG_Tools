"""命令行交互界面 — 适配新应用服务结构。

启动::

    python main.py

模式: chat | rag | graph-rag | agent | multi | build
"""

from __future__ import annotations

import shutil
import textwrap

from application.services.agent_application import AgentApplication


async def run_cli() -> None:
    """异步 CLI 主循环。"""
    app = AgentApplication()
    await app.init_session_store()

    print("=" * 60)
    print("  多 Agent 智能助手系统")
    print("  模式: chat | rag | graph-rag | agent | multi | build")
    print("  输入 '/mode <模式>' 切换, 输入 '退出' 结束")
    print("  粘贴多行文本时, 以 '###' 单独一行结束输入")
    print("=" * 60)

    current_mode = "chat"

    def get_terminal_width() -> int:
        try:
            return shutil.get_terminal_size(fallback=(80, 24)).columns
        except Exception:
            return 80

    def wrap_text(text: str, width: int | None = None) -> str:
        target_width = width if width is not None else get_terminal_width()
        if target_width < 40:
            target_width = 40
        wrapped_lines: list[str] = []
        for original_line in text.split("\n"):
            if len(original_line) <= target_width:
                wrapped_lines.append(original_line)
            else:
                wrapped_lines.append(
                    textwrap.fill(
                        original_line,
                        width=target_width,
                        replace_whitespace=False,
                        drop_whitespace=False,
                        break_long_words=True,
                    )
                )
        return "\n".join(wrapped_lines)

    def print_response(text: str) -> None:
        print(wrap_text(text))
        print()

    def read_multiline() -> str | None:
        try:
            first_line = input(f"\n[{current_mode}] 你: ")
        except EOFError:
            return None

        stripped_first = first_line.rstrip()
        is_paste_command = stripped_first == "/paste"
        is_backslash_trigger = stripped_first.endswith("\\")

        if not is_paste_command and not is_backslash_trigger:
            return first_line.strip()

        collected_lines: list[str] = []
        if not is_paste_command:
            collected_lines.append(stripped_first[:-1])

        while True:
            try:
                next_line = input("... ")
            except EOFError:
                break
            if next_line.rstrip() == "###":
                break
            collected_lines.append(next_line)

        if not collected_lines:
            return ""

        numbered = [f"[line #{i}] {line}" for i, line in enumerate(collected_lines, start=1)]
        return "\n".join(numbered)

    while True:
        try:
            user_input = read_multiline()
            if user_input is None:
                print("再见")
                break

            if user_input.lower() in ["退出", "quit", "exit"]:
                print("再见!")
                break

            if not user_input:
                continue

            if user_input.startswith("/mode"):
                new_mode = user_input.split()[-1].strip()
                if new_mode in ("chat", "rag", "graph-rag", "agent", "multi", "consult", "build"):
                    current_mode = new_mode
                    print(f"已切换到 {current_mode} 模式")
                else:
                    print(f"未知模式: {new_mode}")
                continue

            if current_mode == "chat":
                response = await app.ask_chat(user_input)
            elif current_mode == "rag":
                answer, sources = await app.ask_rag(user_input)
                response = answer
                if sources:
                    response += f"\n\n[sources: {len(sources)}]"
            elif current_mode == "consult":
                answer, sources = await app.ask_consult(user_input, session_id="cli")
                response = answer
                if sources:
                    response += f"\n\n[sources: {len(sources)}]"
            elif current_mode == "graph-rag":
                answer, sources = await app.ask_graph_rag(user_input)
                response = answer
                if sources:
                    response += f"\n\n[sources: {len(sources)}]"
            elif current_mode == "agent":
                response = await app.ask_agent(user_input)
            elif current_mode == "multi":
                multi = await app.ask_multi_agent(user_input)
                response = multi.get("final_answer", "")
            elif current_mode == "build":
                count = app.build_knowledge_base(user_input)
                response = f"知识库构建完成, 共加载 {count} 个文档片段"
            else:
                response = f"未知模式: {current_mode}"

            print_response(f"助手: {response}")

        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            print(f"错误: {e}")
