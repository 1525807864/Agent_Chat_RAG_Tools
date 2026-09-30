// ============================================================================
// KnowledgePanel.tsx：上传文档 → 一键建库（用户不用填服务器路径）
// ============================================================================

import { useCallback, useEffect, useState } from "react";
import {
  buildKnowledge,
  getGraphStats,
  listKnowledgeDocs,
  uploadKnowledgeDoc,
} from "../api/endpoints";
import type { DocInfo } from "../types/api";

// 与后端 ALLOWED_UPLOAD_SUFFIXES / DocumentLoader 白名单对齐
const ACCEPT =
  ".pdf,.txt,.md,.html,.csv,.json,.docx,.xlsx,application/pdf," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function KnowledgePanel() {
  // 任一请求进行中时锁定交互
  const [busy, setBusy] = useState(false);
  // 当前租户已上传文件列表
  const [docs, setDocs] = useState<DocInfo[]>([]);
  // 建库结果文案
  const [buildMsg, setBuildMsg] = useState<string | null>(null);
  // 图谱统计 JSON 文本
  const [statsText, setStatsText] = useState<string | null>(null);
  // 错误条
  const [err, setErr] = useState<string | null>(null);
  // 上传进度提示
  const [uploadHint, setUploadHint] = useState<string | null>(null);

  // 刷新文档列表（GET /api/knowledge/docs）
  const refreshDocs = useCallback(async () => {
    const res = await listKnowledgeDocs();
    setDocs(res.docs || []);
  }, []);

  // 面板挂载时拉一次列表
  useEffect(() => {
    void refreshDocs().catch((e) => {
      setErr(e instanceof Error ? e.message : String(e));
    });
  }, [refreshDocs]);

  // 选择文件后逐个上传到租户 docs
  const onPickFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBusy(true);
    setErr(null);
    setUploadHint(null);
    try {
      const names: string[] = [];
      for (const file of Array.from(files)) {
        setUploadHint(`正在上传：${file.name} …`);
        const res = await uploadKnowledgeDoc(file);
        names.push(`${res.path} (${res.size} bytes)`);
      }
      setUploadHint(`上传完成：${names.join("，")}`);
      await refreshDocs();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // 一键建库：开发期走同步 /build，避免 async + reload 卡在 10%
  const onBuild = async () => {
    setBusy(true);
    setErr(null);
    setBuildMsg("同步构建中，请稍候…（向量入库较慢属正常）");
    try {
      const res = await buildKnowledge({});
      setBuildMsg(
        res.message || `构建完成，分块数：${res.chunk_count ?? 0}`
      );
    } catch (e) {
      setBuildMsg(null);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // 拉图谱统计
  const onStats = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await getGraphStats();
      setStatsText(JSON.stringify(res.stats, null, 2));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="panel">
      <div className="panel-header">知识库</div>
      <div className="panel-body">
        <div className="kb-form">
          <label className="muted" htmlFor="kb-upload">
            上传文档（pdf / docx / xlsx / txt / md …）
          </label>
          <input
            id="kb-upload"
            type="file"
            multiple
            accept={ACCEPT}
            disabled={busy}
            onChange={(e) => {
              void onPickFiles(e.target.files);
              // 清空 value，允许重复选择同一文件
              e.target.value = "";
            }}
          />

          <button
            type="button"
            className="btn primary"
            onClick={() => void onBuild()}
            disabled={busy}
          >
            构建知识库
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => void refreshDocs().catch((e) => setErr(String(e)))}
            disabled={busy}
          >
            刷新列表
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => void onStats()}
            disabled={busy}
          >
            图谱统计
          </button>
        </div>

        {uploadHint && <div className="kb-result">{uploadHint}</div>}
        {err && (
          <div className="error-banner" style={{ margin: "12px 0 0" }}>
            {err}
          </div>
        )}
        {buildMsg && <div className="kb-result">{buildMsg}</div>}

        <div className="kb-stats" style={{ marginTop: 12 }}>
          <strong>已上传文件（{docs.length}）</strong>
          {"\n"}
          {docs.length === 0
            ? "（空）请先选择文件上传"
            : docs.map((d) => `${d.path}  ·  ${d.size} bytes`).join("\n")}
        </div>

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
