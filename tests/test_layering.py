"""分层闸门：domain / api 禁止直接依赖 langchain。"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _langchain_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return [f"<syntax error in {path}>"]
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "langchain" or alias.name.startswith("langchain."):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "langchain" or node.module.startswith("langchain"):
                found.append(node.module)
    return found


def _py_files(rel_dir: str) -> list[Path]:
    base = ROOT / rel_dir
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _assert_no_langchain(rel_dir: str) -> None:
    offenders: list[str] = []
    for path in _py_files(rel_dir):
        hits = _langchain_imports(path)
        if hits:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {hits}")
    assert offenders == [], f"{rel_dir}/ 不得依赖 langchain:\n" + "\n".join(offenders)


def test_domain_has_no_langchain_imports():
    _assert_no_langchain("domain")


def test_api_has_no_langchain_imports():
    _assert_no_langchain("api")
