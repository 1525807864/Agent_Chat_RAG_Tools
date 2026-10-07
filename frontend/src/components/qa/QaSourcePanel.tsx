/**
 * QaSourcePanel.tsx
 * 右栏：内容来源下拉 + 表 + 用例明细 + 最近运行
 */
import { useMemo, useState } from "react";
import type { QaCase, QaProject, QaRun } from "../../types/qa";

type Props = {
  project: QaProject;
  selected: QaCase | null;
  runs: QaRun[];
  busy: boolean;
  onUpload: (file: File) => void;
};

export function QaSourcePanel({
  project,
  selected,
  runs,
  busy,
  onUpload,
}: Props) {
  const [docId, setDocId] = useState(project.sourceDocs[0]?.id || "");
  const doc = useMemo(
    () =>
      project.sourceDocs.find((d) => d.id === docId) || project.sourceDocs[0],
    [project.sourceDocs, docId],
  );

  return (
    <aside className="qa-pane qa-pane-source">
      <div className="qa-pane-head">
        <span>内容来源</span>
      </div>

      <div className="qa-source-toolbar">
        <select
          className="qa-select"
          value={doc?.id || ""}
          onChange={(e) => setDocId(e.target.value)}
        >
          {project.sourceDocs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
          {!project.sourceDocs.length ? (
            <option value="">暂无文档</option>
          ) : null}
        </select>
        <label className="qa-btn qa-btn-file">
          解析文档
          <input
            type="file"
            hidden
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      {doc ? (
        <>
          <table className="qa-table">
            <thead>
              <tr>
                <th>No.</th>
                <th>名称</th>
                <th>ID</th>
                <th>描述</th>
              </tr>
            </thead>
            <tbody>
              {doc.rows.map((r) => (
                <tr key={r.reqId + r.no}>
                  <td>{r.no}</td>
                  <td>{r.name}</td>
                  <td>{r.reqId}</td>
                  <td>{r.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="qa-source-excerpt">
            <strong>摘录</strong>
            <p>{doc.excerpt}</p>
          </div>
        </>
      ) : (
        <p className="qa-empty">
          上传本地 txt/md 文本文件作为来源（壳阶段只读文本）。
        </p>
      )}

      {selected ? (
        <div className="qa-case-sheet">
          <h4>当前条目明细</h4>
          <dl className="qa-dl">
            <dt>用例名称</dt>
            <dd>{selected.title}</dd>
            <dt>编号</dt>
            <dd>{selected.code}</dd>
            <dt>简要描述</dt>
            <dd>{selected.fused || selected.requirement}</dd>
            <dt>前置条件</dt>
            <dd>已配置被测环境；来源文档已确认</dd>
          </dl>
        </div>
      ) : null}

      <div className="qa-runs-block">
        <h4>最近运行</h4>
        <ul className="qa-runs">
          {runs.map((r) => (
            <li
              key={r.id}
              className={
                r.verdict === "pass" ? "qa-run is-pass" : "qa-run is-fail"
              }
            >
              <strong>{r.verdict}</strong> {r.summary}
            </li>
          ))}
          {!runs.length ? <li className="qa-empty">尚无执行记录</li> : null}
        </ul>
      </div>
    </aside>
  );
}
