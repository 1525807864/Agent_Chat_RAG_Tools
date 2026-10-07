/**
 * QaProjectSettings.tsx
 * 项目设置抽屉：名称 / Base URL / 目标
 */
import { useEffect, useState } from "react";
import type { QaProject } from "../../types/qa";

type Props = {
  open: boolean;
  project: QaProject;
  busy: boolean;
  onClose: () => void;
  onSave: (patch: { name: string; baseUrl: string; goal: string }) => void;
};

export function QaProjectSettings({
  open,
  project,
  busy,
  onClose,
  onSave,
}: Props) {
  const [name, setName] = useState(project.name);
  const [baseUrl, setBaseUrl] = useState(project.baseUrl);
  const [goal, setGoal] = useState(project.goal);

  useEffect(() => {
    setName(project.name);
    setBaseUrl(project.baseUrl);
    setGoal(project.goal);
  }, [project.id, project.name, project.baseUrl, project.goal, open]);

  if (!open) return null;

  return (
    <div className="qa-drawer-mask" onClick={onClose}>
      <div
        className="qa-drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="项目设置"
      >
        <div className="qa-drawer-head">
          <h3>项目设置</h3>
          <button type="button" className="qa-link-btn" onClick={onClose}>
            关闭
          </button>
        </div>
        <label className="qa-label">
          项目名称
          <input
            className="qa-field"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="qa-label">
          Base URL
          <input
            className="qa-field"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://example.com"
          />
        </label>
        <label className="qa-label">
          测试目标
          <textarea
            className="qa-field"
            rows={4}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="qa-btn qa-btn-primary"
          disabled={busy}
          onClick={() => onSave({ name, baseUrl, goal })}
        >
          保存
        </button>
      </div>
    </div>
  );
}
