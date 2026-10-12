/**
 * 知识库：Tab1 项目资料（QA sources） / Tab2 租户知识库（复用 KnowledgePanel）
 */
import { Tabs, Typography, Upload, List } from "antd";
import { CloudUploadOutlined } from "@ant-design/icons";
import { KnowledgePanel } from "../KnowledgePanel";
import type { QaProject } from "../../types/qa";

export function QaKnowledgePage({
  project,
  busy,
  onUpload,
}: {
  project: QaProject;
  busy: boolean;
  onUpload: (file: File) => void;
}) {
  return (
    <section className="qa-pane qa-center-page">
      <Tabs
        items={[
          {
            key: "project",
            label: "项目资料",
            children: (
              <>
                <Typography.Paragraph type="secondary">
                  上传到当前项目，供「测试内容」融合与助手使用（POST /sources）。
                </Typography.Paragraph>
                <Upload.Dragger
                  multiple={false}
                  showUploadList={false}
                  accept=".pdf,.txt,.md,.docx"
                  disabled={busy}
                  beforeUpload={(file) => {
                    onUpload(file);
                    return false;
                  }}
                >
                  <p>
                    <CloudUploadOutlined /> 拖拽或点击上传
                  </p>
                </Upload.Dragger>
                <List
                  style={{ marginTop: 16 }}
                  header="已关联资料"
                  dataSource={project.sourceDocs || []}
                  locale={{ emptyText: "暂无资料" }}
                  renderItem={(d) => (
                    <List.Item>
                      <List.Item.Meta
                        title={d.name}
                        description={d.excerpt || d.kind}
                      />
                    </List.Item>
                  )}
                />
              </>
            ),
          },
          {
            key: "tenant",
            label: "租户知识库",
            children: <KnowledgePanel />, // 已接 /api/knowledge，绝不重写
          },
        ]}
      />
    </section>
  );
}