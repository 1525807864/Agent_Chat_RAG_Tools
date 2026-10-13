/**
 * QaCaseDetail.tsx
 * 中栏：标题操作 + 原始需求卡片 + 智能融合 + 步骤期望
 */
import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  CheckOutlined,
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import type { QaCase, QaProject } from "../../types/qa";
import { KIND_LABEL, STATUS_LABEL } from "../../qa/kindLabels";

type Props = {
  project: QaProject;
  selected: QaCase | null;
  busy: boolean;
  /** admin 才能确认 / 删除 / 生成 */
  canWrite?: boolean;
  onConfirm: (fused: string) => void;
  onGenerate: () => void;
  onDelete: (id: string) => void;
};

export function QaCaseDetail({
  project,
  selected,
  busy,
  canWrite = true,
  onConfirm,
  onGenerate,
  onDelete,
}: Props) {
  const [fused, setFused] = useState("");
  useEffect(() => {
    setFused(selected?.fused || "");
  }, [selected?.id, selected?.fused]);

  if (!selected) {
    return (
      <section className="qa-pane qa-pane-detail">
        <Empty description="请从左侧选择一条测试内容，或先生成测试项。" />
      </section>
    );
  }

  const docs = project.sourceDocs.filter((d) =>
    selected.sourceDocIds.length
      ? selected.sourceDocIds.includes(d.id)
      : true,
  );

  return (
    <section className="qa-pane qa-pane-detail">
      <div className="qa-detail-head">
        <div>
          <Space size={6} wrap style={{ marginBottom: 4 }}>
            <Tag>{selected.code}</Tag>
            <Tag color="processing">{KIND_LABEL[selected.kind]}</Tag>
            <Tag color="default">
              {STATUS_LABEL[selected.status] || selected.status}
            </Tag>
          </Space>
          <Typography.Title level={4} className="qa-detail-title">
            {selected.title}
          </Typography.Title>
        </div>
        {canWrite ? (
          <Space wrap>
            <Button
              icon={<CheckOutlined />}
              disabled={busy}
              onClick={() => onConfirm(fused)}
            >
              确认
            </Button>
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={busy}
              onClick={() => onDelete(selected.id)}
            >
              删除
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={busy}
              onClick={onGenerate}
            >
              生成测试项
            </Button>
          </Space>
        ) : null}
      </div>

      <Typography.Text type="secondary" className="qa-section-label">
        原始需求条目
      </Typography.Text>
      <div className="qa-req-cards">
        {docs.length ? (
          docs.map((d) => (
            <Card key={d.id} size="small" title={d.name} className="qa-req-card-ant">
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                {d.excerpt}
              </Typography.Paragraph>
            </Card>
          ))
        ) : (
          <Card size="small" title="（无关联文档，使用条目原文）">
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {selected.requirement}
            </Typography.Paragraph>
          </Card>
        )}
      </div>

      <div className="qa-fuse-divider">
        <span>智能融合处理</span>
      </div>

      <div className="qa-section-label-row">
        <Typography.Text type="secondary">智能融合需求</Typography.Text>
        <Button
          type="link"
          size="small"
          icon={<CopyOutlined />}
          onClick={() => {
            void navigator.clipboard?.writeText(fused);
          }}
        >
          复制
        </Button>
      </div>
      <Input.TextArea
        className="qa-fuse-area"
        value={fused}
        onChange={(e) => setFused(e.target.value)}
        rows={6}
        readOnly={!canWrite}
      />

      <Typography.Text type="secondary" className="qa-section-label">
        步骤 / 期望
      </Typography.Text>
      <ul className="qa-steps">
        {selected.steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
      <Typography.Paragraph>
        期望：{selected.expected}
      </Typography.Paragraph>
    </section>
  );
}
