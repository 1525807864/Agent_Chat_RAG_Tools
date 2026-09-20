// ============================================================================
// SessionList.tsx：左侧会话列表
// - 标题：该会话最后一条用户问题的开头（不是 session id）
// - 单条删除：DELETE /api/sessions/{id}
// - 全部删除：对当前列表逐个调用同一删除接口（后端没有批量删除路由）
// ============================================================================

import { useCallback, useEffect, useState } from "react";
import { deleteSession, getSessionHistory, listSessions } from "../api/endpoints";

// 标题最多显示这么多字，超出用省略号；完整原文放在按钮 title 上
const TITLE_MAX = 24;

type Props = {
  currentId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
};

// 列表里一条：id 用来选中/删除，title 用来展示
type SessionRow = {
  id: string;
  title: string;
};

// 从历史里找「最后一条用户问题」，截取开头当标题
function titleFromHistory(
  id: string,
  messages: { role: string; content: string }[],
): string {
  // 后端历史 role 是 "user"（见 agent_application.get_chat_history）
  const users = messages.filter((m) => m.role === "user" && m.content.trim());
  const last = users[users.length - 1];
  if (!last) return id; // 没有用户消息时仍显示 id，避免空白行
  const text = last.content.replace(/\s+/g, " ").trim();
  if (text.length <= TITLE_MAX) return text;
  return text.slice(0, TITLE_MAX) + "…";
}

export function SessionList({ currentId, onSelect, onNew }: Props) {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // withTitles=false：只拉 id 列表，不逐条 GET 历史（全部删除后用，避免 429）
  const refresh = useCallback(async (withTitles = true) => {
    setLoading(true);
    setErr(null);
    try {
      const res = await listSessions();
      if (!withTitles) {
        setRows(res.sessions.map((id) => ({ id, title: id })));
        return;
      }
      // 列表接口只有 id。标题要另拉每条历史，取最后一条 user 消息开头。
      // 会话通常不多；某一条历史失败时退回显示 id，不让整表失败。
      const next = await Promise.all(
        res.sessions.map(async (id) => {
          try {
            const hist = await getSessionHistory(id);
            return { id, title: titleFromHistory(id, hist.messages) };
          } catch {
            return { id, title: id };
          }
        }),
      );
      setRows(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onDelete = async (id: string) => {
    if (!confirm(`确定删除会话「${id}」的后端历史？`)) return;
    try {
      await deleteSession(id);
      if (id === currentId) onNew();
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  // 全部删除：确认后对当前 rows 逐个 DELETE，再刷新；当前会话被删则新建
  const onDeleteAll = async () => {
    if (rows.length === 0) return;
    if (!confirm(`确定删除全部 ${rows.length} 条会话历史？此操作不可恢复。`)) return;
    setLoading(true);
    setErr(null);
    try {
      const ids = rows.map((r) => r.id);
      // 串行删除，避免一次打满限流；失败则停在该条并提示
      for (const id of ids) {
        await deleteSession(id);
      }
      if (ids.includes(currentId)) onNew();
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      await refresh(); // 可能已经删掉一部分，刷新成剩余列表
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="panel">
      <div className="panel-header">
        <span>会话</span>
        <div style={{ display: "flex", gap: 6 }}>
          <button type="button" className="btn" onClick={onNew} title="新建本地 session_id">
            新建
          </button>
          <button type="button" className="btn" onClick={() => void refresh()} disabled={loading}>
            刷新
          </button>
          <button
            type="button"
            className="btn danger"
            onClick={onDeleteAll}
            disabled={loading || rows.length === 0}
            title="删除当前列表中的全部会话历史"
          >全部删除</button>
        </div>
      </div>
      <div className="panel-body">
        <p className="muted" style={{ marginTop: 0 }}>
          当前：<code>{currentId}</code>
        </p>
        {err && <p className="error-banner">{err}</p>}
        {loading && rows.length === 0 && <p className="muted">加载中…</p>}
        {!loading && rows.length === 0 && (
          <p className="muted">暂无后端历史（chat 模式发过消息才会出现）</p>
        )}
        {rows.map((row) => (
          <div className="session-item" key={row.id}>
            <button
              type="button"
              className={`pick${row.id === currentId ? " active" : ""}`}
              onClick={() => onSelect(row.id)}
              title={`${row.title}\n${row.id}`}
            >
              {row.title}
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={() => void onDelete(row.id)}
              title="DELETE /api/sessions/{id}"
            >
              删除
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}