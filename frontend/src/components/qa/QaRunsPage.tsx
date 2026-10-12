/**
 * 执行记录：名称 + 目标 + URL，开始智能 UI 测试（真开浏览器）。
 * 步骤实时出现在右侧助手栏；结束后可导出 xlsx/docx/pdf。
 */
import { useEffect, useState } from "react";
import { Button, Empty, Input, List, Space, Tag, Typography } from "antd";
import { DownloadOutlined, PlayCircleOutlined } from "@ant-design/icons";
import type { QaRun } from "../../types/qa";

export function QaRunsPage({
  runs,
  defaultUrl,
  busy,
  uiRunning,
  onSmoke,
  onUi,
  onExport,
}: {
  runs: QaRun[];
  defaultUrl: string;
  busy: boolean;
  uiRunning: boolean;
  onSmoke: () => void;
  onUi: (name: string, url: string, goal: string) => void;
  onExport: (runId: string, fmt: "xlsx" | "docx" | "pdf") => void;
}) {
  const [name, setName] = useState("打开站点探活");
  const [url, setUrl] = useState(defaultUrl);
  const [goal, setGoal] = useState("打开页面，确认标题可见，并截取首页关键区域");

  useEffect(() => {
    setUrl(defaultUrl);
  }, [defaultUrl]);

  return (
    <section className="qa-pane qa-center-page">
      <div className="qa-pane-head">
        <span>执行记录</span>
        <Button
          icon={<PlayCircleOutlined />}
          loading={busy && !uiRunning}
          disabled={uiRunning}
          onClick={onSmoke}
        >
          执行冒烟（HTTP）
        </Button>
      </div>

      <Space
        direction="vertical"
        size={8}
        style={{ width: "100%", marginBottom: 16 }}
      >
        <Typography.Text type="secondary">
          智能 UI 测试：本机弹出浏览器，模型按目标逐步操作；右侧同步每一步，结束后可导出证据。
        </Typography.Text>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="测试名称"
        />
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://被测站点"
        />
        <Input.TextArea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="测试目标（给模型执行，例如：登录后进入订单列表并确认有数据）"
          rows={3}
          maxLength={4000}
        />
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={uiRunning}
          disabled={busy && !uiRunning}
          onClick={() => onUi(name, url, goal)}
        >
          开始智能 UI 测试
        </Button>
      </Space>

      {runs.length ? (
        <List
          dataSource={runs}
          renderItem={(r) => (
            <List.Item
              actions={[
                <Button
                  key="xlsx"
                  type="link"
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => onExport(r.id, "xlsx")}
                >
                  Excel
                </Button>,
                <Button
                  key="docx"
                  type="link"
                  size="small"
                  onClick={() => onExport(r.id, "docx")}
                >
                  Word
                </Button>,
                <Button
                  key="pdf"
                  type="link"
                  size="small"
                  onClick={() => onExport(r.id, "pdf")}
                >
                  PDF
                </Button>,
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Tag color={r.verdict === "pass" ? "success" : "error"}>
                    {r.verdict}
                  </Tag>
                }
                title={<Typography.Text>{r.summary}</Typography.Text>}
                description={
                  <Typography.Text type="secondary">{r.id}</Typography.Text>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty description="还没有执行。" />
      )}
    </section>
  );
}
