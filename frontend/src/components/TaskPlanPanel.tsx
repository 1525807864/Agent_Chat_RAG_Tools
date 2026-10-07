/**
 * TaskPlanPanel：意图追踪面板
 * ------------------------------------------------
 * 展示 Intent Guard 的会话级台账：
 * - 意图卡片：用户最初目标（锚点） + 转向历史
 * - 任务清单：子任务状态 chip + 进度条
 * - 最近检查：drift 拦截 / aligned 记录
 * 无数据（旧后端 / guard 关闭）时不渲染。
 */
import { useState } from "react";
import type { TaskCheckEvent, TaskPlan } from "../types/api";

interface Props {
  taskPlan: TaskPlan | null;
  lastCheck: TaskCheckEvent | null;
}

/** 状态 → 中文标签 */
const STATUS_LABEL: Record<string, string> = {
  pending: "待办",
  in_progress: "进行中",
  done: "已完成",
  blocked: "已搁置",
  skipped: "已放弃",
};

export function TaskPlanPanel({ taskPlan, lastCheck }: Props) {
  // 转向历史折叠开关
  const [showHistory, setShowHistory] = useState(false);

  if (!taskPlan || !taskPlan.goal) {
    return null;
  }

  const tasks = taskPlan.tasks || [];
  const countable = tasks.filter((t) => t.status !== "skipped");
  const score = countable.reduce((sum, t) => {
    if (t.status === "done") return sum + 1;
    if (t.status === "in_progress") return sum + 0.5;
    return sum;
  }, 0);
  const total = countable.length;
  const pct = total > 0 ? Math.round((score / total) * 100) : 0;
  const history = taskPlan.anchor_history || [];

  return (
    <section className="task-panel" aria-label="意图追踪">
      {/* 意图卡片：锚点目标 */}
      <div className="task-panel-goal">
        <span className="task-panel-title">🎯 用户目标</span>
        <p className="task-panel-goal-text">{taskPlan.goal}</p>
        {history.length > 0 && (
          <button
            type="button"
            className="task-panel-history-toggle"
            onClick={() => setShowHistory((v) => !v)}
          >
            {showHistory ? "收起" : "展开"}转向历史（{history.length}）
          </button>
        )}
        {showHistory &&
          history.map((h, i) => (
            <p key={i} className="task-panel-history-item">
              旧目标：{h.goal}
              {h.reason ? `（${h.reason}）` : ""}
            </p>
          ))}
      </div>

      {/* 任务清单 + 进度 */}
      {total > 0 && (
        <div className="task-panel-tasks">
          <div className="task-panel-progress">
            <div
              className="task-panel-progress-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="task-panel-progress-label">
            {score}/{total} 完成
          </span>
          <ul className="task-panel-list">
            {tasks.map((t) => (
              <li key={t.id} className={`task-item ${t.status}`}>
                <span className={`task-chip ${t.status}`}>
                  {STATUS_LABEL[t.status] || t.status}
                </span>
                <span className="task-item-title">{t.title}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 最近一次对齐检查 */}
      {lastCheck && lastCheck.verdict && (
        <div className={`task-panel-check ${lastCheck.verdict}`}>
          {lastCheck.verdict === "drift"
            ? `⚠️ 第 ${lastCheck.step ?? "?"} 步被拦截：${lastCheck.reason || ""}`
            : `✅ 最近检查：${lastCheck.reason || lastCheck.verdict}`}
          {lastCheck.verdict === "drift" && lastCheck.correction ? (
            <p className="task-panel-correction">纠正：{lastCheck.correction}</p>
          ) : null}
        </div>
      )}
    </section>
  );
}
