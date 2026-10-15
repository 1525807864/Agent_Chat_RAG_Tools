# Nexora 评测套件（evals）

与 `tests/power_test` 配合：YAML 题库 + DeepEval / 确定性断言 + Pass@k / Pass^k 门禁。

## 目录

| 路径 | 说明 |
|------|------|
| `suites/` | 自建业务题（按域分子目录） |
| `fixtures/` | 夹具（最小知识库等） |
| `regressions/` | 生产失败回流题 |
| `gold/judge/` | Judge 人标校准（可选） |
| `reports/` | 跑批 JSON（gitignore） |

## 跑 P0 门禁

```powershell
cd D:\LangChain_Demo
$env:PYTHONIOENCODING="utf-8"
$env:EVAL_TAGS="p0"
$env:EVAL_K="1"   # 调试用 1；正式完备用 YAML 里的 k 或设 3
pytest tests/power_test/test_suite_runner.py -v -s
```

## 跑难题（p1 / hard）

```powershell
$env:EVAL_TAGS="hard"   # 或 p1
$env:EVAL_K="1"          # 先烟雾；正式用 YAML 里的 k（多为 3）
pytest tests/power_test/test_suite_runner.py -v -s
```

难题覆盖：零工具寒暄、天气禁编造、工具预算、多约束 Agent、矛盾指令 Chat、RAG 夹具/拒答、混淆越狱。

RAG 题（`suites/rag/*`）使用 `tenant_id=eval`：请先把 `evals/fixtures/kb_min` 灌入该租户，否则夹具题结果不稳定。

轨迹字段：

| 字段 | 含义 |
|------|------|
| `expected_tools` + `match_mode: subset` | 期望工具必须出现（可多调） |
| `expected_tools: []` + `strict` | **零工具** |
| `max_tool_calls` | 调用次数上限（含同名多次） |

## 完备声明

报告路径形如 `evals/reports/p0_YYYYMMDDTHHMMSS.json`。  
P0 全绿且 `pass_mode=pass_hat_k` 时，可声明对应域完备。
