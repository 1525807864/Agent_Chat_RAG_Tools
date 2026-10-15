# 从 evals/suites/**/*.yaml 加载 EvalCase。
# 依赖PyYAML 

from __future__ import annotations 
from pathlib import Path 
from typing import Iterable 
import yaml # 解析yaml文件 
from .eval_schema import (
    EvalCase,
    EvalExpect,
    EvalInput,
    EvalJudge,
    EvalTrajectory,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SUITES = _ROOT / "evals" / "suites"

def _as_dict(raw:object)->dict:
    """YAML根必须是mapping，否则raise ValueError"""
    if not isinstance(raw,dict): 
        raise ValueError(f"YAML根必须是mapping, 不是{type(raw)}")
    return raw 

def dict_to_case(data:dict)->EvalCase:
    """将字典转换为EvalCase"""
    data = _as_dict(data)
    inp = data.get("input") or {}
    exp = data.get("expect") or {}
    jud = data.get("judge") or {}
    trj = data.get("trajectory") or {}
    return EvalCase(
        id=str(data["id"]),  # id 必填，没有就让它炸，方便早发现
        domain=str(data.get("domain") or "E1"),
        tags=[t.strip().lower() for t in data.get("tags") or []],
        pass_mode=data.get("pass_mode") or "pass_hat_k",  # type: ignore[arg-type]
        k=int(data.get("k") or 1),
        input=EvalInput(
            mode=str(inp.get("mode") or "chat"),
            message=str(inp.get("message") or ""),
            tenant_id=str(inp.get("tenant_id") or "default"),
            session_id=inp.get("session_id"),
            multi_mode=str(inp.get("multi_mode") or "sequential"),
            extra=dict(inp.get("extra") or {}),
        ),
        expect=EvalExpect(
            must_contain=list(exp.get("must_contain") or []),
            must_not_contain=list(exp.get("must_not_contain") or []),
            match_any_of_must_contain=bool(
                exp.get("match_any_of_must_contain") or False
            ),
        ),
        judge=EvalJudge(
            type=jud.get("type") or "rubric_llm",  # type: ignore[arg-type]
            threshold=float(jud.get("threshold") if jud.get("threshold") is not None else 0.6),
            criteria=str(jud.get("criteria") or ""),
        ),
        trajectory=EvalTrajectory(
            expected_tools=list(trj.get("expected_tools") or []),
            match_mode=trj.get("match_mode") or "subset",  # type: ignore[arg-type]
            max_tool_calls=(
                int(trj["max_tool_calls"])
                if trj.get("max_tool_calls") is not None
                else None
            ),
        ),
    )

def load_case_file(path:Path)->EvalCase:
    """加载单个用例文件"""
    text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    case = dict_to_case(raw)
    if path.stem != case.id and not path.stem.startswith("case_"):
        print(f"[eval_loader] 提示: 文件 {path.name} 与 id={case.id} 不一致")
    return case 

def iter_suite_files(suites_dir:Path | None = None)->Iterable[Path]:
    """递归枚举suites下所有的 .yaml .yml 文件"""
    root = suites_dir or _DEFAULT_SUITES
    if not root.is_dir():
        return []
    files = list(root.rglob("*.yaml")) + list(root.rglob("*.yml"))
    return sorted(files)

def load_suite(
    *,
    suites_dir:Path | None = None,
    tags_any: set[str] | None = None,
    domains: set[str] | None = None,
)->list[EvalCase]:
    """
    加载套件；可用 tags/domains 过滤（如只要 p0）。
    tags_any：用例 tags 与该集合有交集则保留（大小写不敏感）。
    """
    cases: list[EvalCase] = []
    for path in iter_suite_files(suites_dir):
        case = load_case_file(path)
        if domains and case.domain not in domains:
            continue 
        if tags_any:
            ctags = {t.lower() for t in case.tags}
            want = {t.lower() for t in tags_any}
            if not (ctags & want):
                continue 
        cases.append(case) 
    return cases 

