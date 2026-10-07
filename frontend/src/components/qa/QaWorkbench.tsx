/**
 * QaWorkbench.tsx
 * 项目内工作区：次顶栏 + 左树 / 中详情 / 右来源
 */
import type { QaCase, QaProject, QaRun } from "../../types/qa";
import { QaCaseTree } from "./QaCaseTree";
import { QaCaseDetail } from "./QaCaseDetail";
import { QaSourcePanel } from "./QaSourcePanel";
import { QaProjectSettings } from "./QaProjectSettings";

type Props = {
  project: QaProject;
  cases: QaCase[];
  runs: QaRun[];
  selectedCase: QaCase | null;
  selectedCaseId: string | null;
  treeQuery: string;
  settingsOpen: boolean;
  busy: boolean;
  notice: string;
  onBack: () => void;
  onSelect: (id: string) => void;
  onQuery: (q: string) => void;
  onGenerate: () => void;
  onDelete: (id: string) => void;
  onConfirm: (fused: string) => void;
  onSmoke: () => void;
  onUpload: (file: File) => void;
  onOpenSettings: () => void;
  onCloseSettings: () => void;
  onSaveSettings: (patch: {
    name: string;
    baseUrl: string;
    goal: string;
  }) => void;
};

export function QaWorkbench(props: Props) {
  const {
    project,
    cases,
    runs,
    selectedCase,
    selectedCaseId,
    treeQuery,
    settingsOpen,
    busy,
    notice,
    onBack,
    onSelect,
    onQuery,
    onGenerate,
    onDelete,
    onConfirm,
    onSmoke,
    onUpload,
    onOpenSettings,
    onCloseSettings,
    onSaveSettings,
  } = props;

  return (
    <div className="qa-workbench">
      <div className="qa-subhead">
        <button type="button" className="qa-back" onClick={onBack}>
          ← 返回
        </button>
        <div className="qa-subhead-title">
          {project.name}
          <span className="qa-subhead-muted">项目测试内容</span>
        </div>
        <div className="qa-subhead-actions">
          <button type="button" className="qa-btn" onClick={onOpenSettings}>
            项目设置
          </button>
          <button
            type="button"
            className="qa-btn qa-btn-primary"
            disabled={busy}
            onClick={onSmoke}
          >
            执行冒烟
          </button>
        </div>
      </div>

      {notice ? <div className="qa-notice">{notice}</div> : null}

      <div className="qa-workbench-grid">
        <QaCaseTree
          cases={cases}
          selectedId={selectedCaseId}
          query={treeQuery}
          onQuery={onQuery}
          onSelect={onSelect}
          onGenerate={onGenerate}
          onDelete={onDelete}
          busy={busy}
        />
        <QaCaseDetail
          project={project}
          selected={selectedCase}
          busy={busy}
          onConfirm={onConfirm}
          onGenerate={onGenerate}
          onDelete={onDelete}
        />
        <QaSourcePanel
          project={project}
          selected={selectedCase}
          runs={runs}
          busy={busy}
          onUpload={onUpload}
        />
      </div>

      <QaProjectSettings
        open={settingsOpen}
        project={project}
        busy={busy}
        onClose={onCloseSettings}
        onSave={onSaveSettings}
      />
    </div>
  );
}
