// ============================================================================
// SessionList.tsx：左侧会话列表
// - 标题：该会话最后一条用户问题的开头（不是 session id）
// - 单条删除：DELETE /api/sessions/{id}
// - 全部删除：对当前列表逐个调用同一删除接口（后端没有批量删除路由）
// ============================================================================

import { useCallback, useEffect, useState } from "react";
import { Button, Space, Typography } from "antd";
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { deleteSession, getSessionHistory, listSessions } from "../api/endpoints";

const TITLE_MAX = 24;

type Props = {
  currentId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
};

type SessionRow = {
  id: string;
  title: string;
};

function titleFromHistory(
  id: string,
  messages: { role: string; content: string }[],
): string {
  const users = messages.filter((m) => m.role === "user" && m.content.trim());
  const last = users[users.length - 1];
  if (!last) return id;
  const text = last.content.replace(/\s+/g, " ").trim();
  if (text.length <= TITLE_MAX) return text;
  return text.slice(0, TITLE_MAX) + "…";
}

export function SessionList({ currentId, onSelect, onNew }: Props) {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async (withTitles = true) => {
    setLoading(true);
    setErr(null);
    try {
      const res = await listSessions();
      if (!withTitles) {
        setRows(res.sessions.map((id) => ({ id, title: id })));
        return;
      }
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

  const onDeleteAll = async () => {
    if (rows.length === 0) return;
    if (!confirm(`确定删除全部 ${rows.length} 条会话历史？此操作不可恢复。`))
      return;
    setLoading(true);
    setErr(null);
    try {
      const ids = rows.map((r) => r.id);
      for (const id of ids) {
        await deleteSession(id);
      }
      if (ids.includes(currentId)) onNew();
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="panel">
      <div className="panel-header">
        <span>会话</span>
        <Space size={6}>
          <Button size="small" icon={<PlusOutlined />} onClick={onNew}>
            新建
          </Button>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => void refresh()}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => void onDeleteAll()}
            disabled={loading || rows.length === 0}
          >
            全部
          </Button>
        </Space>
      </div>
      <div className="panel-body">
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          当前：<Typography.Text code>{currentId}</Typography.Text>
        </Typography.Paragraph>
        {err ? <p className="error-banner">{err}</p> : null}
        {loading && rows.length === 0 ? (
          <Typography.Text type="secondary">加载中…</Typography.Text>
        ) : null}
        {!loading && rows.length === 0 ? (
          <Typography.Text type="secondary">
            暂无后端历史（chat 模式发过消息才会出现）
          </Typography.Text>
        ) : null}
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
            <Button
              size="small"
              danger
              type="text"
              icon={<DeleteOutlined />}
              onClick={() => void onDelete(row.id)}
              title="DELETE /api/sessions/{id}"
            />
          </div>
        ))}
      </div>
    </aside>
  );
}
