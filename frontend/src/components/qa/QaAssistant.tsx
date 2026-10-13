/**
 * 右侧助手：上半对话改用例草稿，下半资料（URL / 目标 / 上传 / 最近运行）。
 */
import { useEffect, useState } from "react";
import {
  Button,
  Collapse,
  Input,
  Space,
  Typography,
  Upload,
} from "antd";
import {
  CloudUploadOutlined,
  SaveOutlined,
  SendOutlined,
} from "@ant-design/icons";
import type { QaChatTurn, QaProject, QaRun, QaUiStep } from "../../types/qa";

type Props = {
  project: QaProject | null;
  chat: QaChatTurn[];
  runs: QaRun[];
  busy: boolean;
  materialsOpen: boolean;
  /** admin：助手改用例 */
  canWriteCase?: boolean;
  /** admin：保存环境 / 上传资料 */
  canWriteProject?: boolean;
  onToggleMaterials: () => void;
  onSend: (text: string) => void;
  onUpload: (file: File) => void;
  onSaveEnv: (patch: { name: string; baseUrl: string; goal: string }) => void;
  uiSteps: QaUiStep[];
  uiRunning: boolean;
};

export function QaAssistant({
  project,
  chat,
  runs,
  busy,
  materialsOpen,
  canWriteCase = true,
  canWriteProject = true,
  onToggleMaterials,
  onSend,
  onUpload,
  onSaveEnv,
  uiSteps,
  uiRunning,
}: Props) {
  const [text, setText] = useState("");
  const [baseUrl, setBaseUrl] = useState(project?.baseUrl || "");
  const [goal, setGoal] = useState(project?.goal || "");
  const latest = runs[0];

  useEffect(() => {
    setBaseUrl(project?.baseUrl || "");
    setGoal(project?.goal || "");
  }, [project?.id, project?.baseUrl, project?.goal]);

  return (
    <aside className="qa-assistant">
      <div className="qa-assistant-chat">
        <div className="qa-pane-head">测试助手</div>
        {(uiRunning || uiSteps.length > 0) && (
          <div className="qa-ui-steps">
            <div className="qa-pane-head">
              {uiRunning ? "UI 测试进行中" : "最近 UI 步骤"}
            </div>
            {uiSteps.map((s) => (
              <div
                key={s.i}
                className={`qa-ui-step ${s.ok ? "is-ok" : "is-fail"}`}
              >
                <strong>
                  {s.i}. {s.action}
                </strong>
                <span>{s.ok ? "通过" : "失败"}</span>
                <p>{s.error || s.detail}</p>
              </div>
            ))}
          </div>
        )}
        <div className="qa-chat-log">
          {chat.length === 0 ? (
            <Typography.Paragraph type="secondary" className="qa-empty">
              选中一条用例后，可以说「把性能测试补上 p95 小于 300ms」。
            </Typography.Paragraph>
          ) : (
            chat.map((m) => (
              <div key={m.id} className={`qa-chat-bubble is-${m.role}`}>
                {m.text}
              </div>
            ))
          )}
        </div>
        <form
          className="qa-chat-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            onSend(text);
            setText("");
          }}
        >
          <Input
            value={text}
            disabled={busy || !project || !canWriteCase}
            placeholder={
              !project
                ? "请先进入一个项目"
                : canWriteCase
                  ? "描述要改的用例"
                  : "当前角色不能改用例"
            }
            onChange={(e) => setText(e.target.value)}
          />
          <Button
            type="primary"
            htmlType="submit"
            icon={<SendOutlined />}
            disabled={busy || !project || !canWriteCase}
          >
            发送
          </Button>
        </form>
      </div>

      <div className="qa-materials">
        <Collapse
          ghost
          activeKey={materialsOpen ? ["materials"] : []}
          onChange={(keys) => {
            const open = Array.isArray(keys)
              ? keys.includes("materials")
              : keys === "materials";
            if (open !== materialsOpen) onToggleMaterials();
          }}
          items={[
            {
              key: "materials",
              label: "资料与环境",
              children: project ? (
                <Space direction="vertical" style={{ width: "100%" }} size={12}>
                  <div>
                    <Typography.Text type="secondary">Base URL</Typography.Text>
                    <Input
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder="https://被测站点"
                      disabled={!canWriteProject}
                    />
                  </div>
                  <div>
                    <Typography.Text type="secondary">测试目标</Typography.Text>
                    <Input.TextArea
                      rows={3}
                      value={goal}
                      onChange={(e) => setGoal(e.target.value)}
                      disabled={!canWriteProject}
                    />
                  </div>
                  <Space wrap>
                    <Button
                      icon={<SaveOutlined />}
                      disabled={busy || !canWriteProject}
                      onClick={() =>
                        onSaveEnv({ name: project.name, baseUrl, goal })
                      }
                    >
                      保存环境
                    </Button>
                    <Upload
                      showUploadList={false}
                      accept=".pdf,.txt,.md,.docx"
                      disabled={!canWriteProject}
                      beforeUpload={(file) => {
                        onUpload(file);
                        return false;
                      }}
                    >
                      <Button
                        icon={<CloudUploadOutlined />}
                        disabled={busy || !canWriteProject}
                      >
                        上传文档
                      </Button>
                    </Upload>
                  </Space>
                  <Typography.Text type="secondary">
                    {latest
                      ? `最近运行：${latest.verdict} ${latest.summary}`
                      : "尚无运行"}
                  </Typography.Text>
                </Space>
              ) : (
                <Typography.Text type="secondary">
                  进入项目后可配置环境与资料
                </Typography.Text>
              ),
            },
          ]}
        />
      </div>
    </aside>
  );
}
