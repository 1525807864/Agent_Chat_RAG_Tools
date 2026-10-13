/**
 * QaProjectList.tsx
 * 进项目之前的列表页：卡片进工作区 + 新建表单。
 */
import { useState } from "react";
import { Button, Card, Empty, Input, Space, Typography } from "antd";
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import type { QaProject } from "../../types/qa";

type Props = {
  projects: QaProject[];
  busy: boolean;
  /** admin 才能新建 / 删除项目 */
  canWrite?: boolean;
  onOpen: (id: string) => void;
  onCreate: (name: string, baseUrl: string, goal: string) => void;
  onResetDemo: () => void;
  onDelete: (id: string) => void;
};

export function QaProjectList({
  projects,
  busy,
  canWrite = true,
  onOpen,
  onCreate,
  onResetDemo,
  onDelete,
}: Props) {
  const [name, setName] = useState("新测试项目");
  const [baseUrl, setBaseUrl] = useState("");
  const [goal, setGoal] = useState("");

  return (
    <div className="qa-list-page">
      <div className="qa-list-hero">
        <Typography.Title level={3} className="qa-list-title">
          测试项目空间
        </Typography.Title>
        <Typography.Paragraph type="secondary" className="qa-list-sub">
          选择项目进入测试内容工作台。当前为前端壳，数据保存在浏览器本地。
        </Typography.Paragraph>
      </div>

      {canWrite ? (
        <Card size="small" title="新建项目" className="qa-list-create-card">
          <Space wrap style={{ width: "100%" }}>
            <Input
              style={{ width: 160 }}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="项目名称"
            />
            <Input
              style={{ minWidth: 200, flex: 1 }}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="被测 Base URL（可选）"
            />
            <Input
              style={{ minWidth: 200, flex: 1 }}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="一句话测试目标"
            />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              loading={busy}
              onClick={() => onCreate(name, baseUrl, goal)}
            >
              创建并进入
            </Button>
            <Button
              icon={<ReloadOutlined />}
              disabled={busy}
              onClick={onResetDemo}
              title="清空本地壳数据"
            >
              重置演示
            </Button>
          </Space>
        </Card>
      ) : null}

      <div className="qa-list-grid">
        {projects.map((p) => (
          <Card
            key={p.id}
            hoverable
            className="qa-project-card-ant"
            actions={[
              <Button
                key="open"
                type="link"
                onClick={() => onOpen(p.id)}
              >
                进入工作台
              </Button>,
              ...(canWrite
                ? [
                    <Button
                      key="del"
                      type="link"
                      danger
                      icon={<DeleteOutlined />}
                      disabled={busy}
                      onClick={() => onDelete(p.id)}
                    >
                      删除
                    </Button>,
                  ]
                : []),
            ]}
          >
            <Card.Meta
              title={p.name}
              description={
                <Space direction="vertical" size={4}>
                  <Typography.Text type="secondary">
                    {p.baseUrl || "未配置 Base URL"}
                  </Typography.Text>
                  <Typography.Text type="secondary">
                    {p.goal || "暂无目标"}
                  </Typography.Text>
                  <Typography.Text type="secondary">
                    来源 {p.sourceDocs.length}
                  </Typography.Text>
                </Space>
              }
            />
          </Card>
        ))}
      </div>

      {!projects.length ? (
        <Empty
          style={{ marginTop: 48 }}
          description="还没有项目，先在上方创建一笔"
        />
      ) : null}
    </div>
  );
}
