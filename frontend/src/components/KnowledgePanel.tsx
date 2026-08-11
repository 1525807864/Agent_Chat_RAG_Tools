// ============================================================================
// KnowledgePanel.tsx：右侧知识库 —— 建库 + 图谱统计（组件内自治）
// ============================================================================

// 导入 useState
import { useState } from "react";
// 导入 API
import { buildKnowledge, getGraphStats } from "../api/endpoints";

// 导出面板（无 props）
export function KnowledgePanel() {
  // 文档目录，默认 data/docs
  const [docDir, setDocDir] = useState("data/docs");
  // 请求中锁定按钮
  const [busy, setBusy] = useState(false);
  // 建库结果文案
  const [buildMsg, setBuildMsg] = useState<string | null>(null);
  // 统计 JSON 文本
  const [statsText, setStatsText] = useState<string | null>(null);
  // 错误文案
  const [err, setErr] = useState<string | null>(null);

  // 构建知识库
  const onBuild = async () => {
    setBusy(true); // 开始忙碌
    setErr(null); // 清错误
    setBuildMsg(null); // 清旧结果
    try {
      // 调后端建库
      const res = await buildKnowledge({ doc_dir: docDir.trim() });
      // 拼展示文案
      setBuildMsg(`${res.message}\n分块数：${res.chunk_count}\n目录：${res.doc_dir}`);
    } catch (e) {
      // 失败写入 err
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false); // 结束忙碌
    }
  };

  // 拉图谱统计
  const onStats = async () => {
    setBusy(true); // 忙碌
    setErr(null); // 清错误
    try {
      const res = await getGraphStats(); // 请求
      setStatsText(JSON.stringify(res.stats, null, 2)); // 美化 JSON
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e)); // 错误
    } finally {
      setBusy(false); // 解锁
    }
  };

  // 渲染
  return (
    <aside className="panel">
      <div className="panel-header">知识库</div>
      <div className="panel-body">
        <div className="kb-form">
          {/* 目录输入标签 */}
          <label className="muted" htmlFor="doc-dir">
            文档目录（POST /api/knowledge/build）
          </label>
          {/* 目录输入框 */}
          <input
            id="doc-dir"
            value={docDir} // 受控
            onChange={(e) => setDocDir(e.target.value)} // 更新
            placeholder="data/docs"
            disabled={busy} // 忙碌时禁用
          />
          {/* 建库按钮 */}
          <button type="button" className="btn primary" onClick={() => void onBuild()} disabled={busy}>
            构建知识库
          </button>
          {/* 统计按钮 */}
          <button type="button" className="btn" onClick={() => void onStats()} disabled={busy}>
            图谱统计
          </button>
        </div>
        {/* 错误条 */}
        {err && <div className="error-banner" style={{ margin: "12px 0 0" }}>{err}</div>}
        {/* 建库结果 */}
        {buildMsg && <div className="kb-result">{buildMsg}</div>}
        {/* 统计结果 */}
        {statsText && (
          <div className="kb-stats">
            <strong>GET /api/knowledge/graph/stats</strong>
            {"\n"}
            {statsText}
          </div>
        )}
      </div>
    </aside>
  );
}
