// ============================================================================
// SessionList.tsx：左侧会话列表 —— 刷新/新建/删除/选中
// ============================================================================

// 导入 Hook
import { useCallback, useEffect, useState } from "react";
// 导入会话 API
import { deleteSession, listSessions } from "../api/endpoints";

// Props
type Props = {
  currentId: string; // 当前会话 id
  onSelect: (id: string) => void; // 选中回调
  onNew: () => void; // 新建回调
};

// 导出侧栏
export function SessionList({ currentId, onSelect, onNew }: Props) {
  // 后端返回的 id 列表
  const [sessions, setSessions] = useState<string[]>([]);
  // 列表加载中
  const [loading, setLoading] = useState(false);
  // 错误信息
  const [err, setErr] = useState<string | null>(null);

  // 刷新列表
  const refresh = useCallback(async () => {
    setLoading(true); // 开始加载
    setErr(null); // 清错误
    try {
      const res = await listSessions(); // 请求
      setSessions(res.sessions); // 写入列表
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e)); // 记录错误
    } finally {
      setLoading(false); // 结束加载
    }
  }, []);

  // 挂载时刷一次
  useEffect(() => {
    void refresh(); // 忽略 Promise
  }, [refresh]);

  // 删除某会话
  const onDelete = async (id: string) => {
    // 二次确认
    if (!confirm(`确定删除会话「${id}」的后端历史？`)) return;
    try {
      await deleteSession(id); // 调删除 API
      // 删的是当前会话 → 新建本地会话
      if (id === currentId) onNew();
      await refresh(); // 刷新列表
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e)); // 错误
    }
  };

  // 渲染
  return (
    <aside className="panel">
      {/* 标题栏 */}
      <div className="panel-header">
        <span>会话</span>
        <div style={{ display: "flex", gap: 6 }}>
          {/* 新建 */}
          <button type="button" className="btn" onClick={onNew} title="新建本地 session_id">
            新建
          </button>
          {/* 刷新 */}
          <button type="button" className="btn" onClick={() => void refresh()} disabled={loading}>
            刷新
          </button>
        </div>
      </div>
      {/* 列表体 */}
      <div className="panel-body">
        {/* 当前 id */}
        <p className="muted" style={{ marginTop: 0 }}>
          当前：<code>{currentId}</code>
        </p>
        {/* 错误 */}
        {err && <p className="error-banner">{err}</p>}
        {/* 首屏加载 */}
        {loading && sessions.length === 0 && <p className="muted">加载中…</p>}
        {/* 空列表提示 */}
        {!loading && sessions.length === 0 && (
          <p className="muted">暂无后端历史（chat 模式发过消息才会出现）</p>
        )}
        {/* 逐条会话 */}
        {sessions.map((id) => (
          <div className="session-item" key={id}>
            {/* 选中按钮 */}
            <button
              type="button"
              className={`pick${id === currentId ? " active" : ""}`} // 当前高亮
              onClick={() => onSelect(id)} // 通知父级
              title={id}
            >
              {id}
            </button>
            {/* 删除按钮 */}
            <button
              type="button"
              className="btn danger"
              onClick={() => void onDelete(id)}
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
