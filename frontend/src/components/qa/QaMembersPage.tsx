import { useState } from "react";
import { Button, Input, Select, Space, Table, Typography } from "antd";
import { DeleteOutlined, UserAddOutlined } from "@ant-design/icons";
import type { QaMember, QaMemberRole } from "../../types/qa";

const ROLES: QaMemberRole[] = ["admin", "execute", "view"];
const ROLE_CN: Record<QaMemberRole, string> = {
  admin: "可管理",
  execute: "可执行",
  view: "可查看",
};

export function QaMembersPage({
  tenantId,
  members,
  onAdd,
  onRole,
  onDelete,
}: {
  tenantId: string;
  members: QaMember[];
  onAdd: (name: string, role: QaMemberRole) => void;
  onRole: (id: string, role: QaMemberRole) => void;
  onDelete?: (id: string) => void;
}) {
  const [name, setName] = useState("");
  return (
    <section className="qa-pane qa-center-page">
      <div className="qa-pane-head">
        <span>
          成员权限 ·{" "}
          <Typography.Text type="secondary">{tenantId}</Typography.Text>
        </span>
      </div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          style={{ width: 200 }}
          value={name}
          placeholder="成员名"
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          type="primary"
          icon={<UserAddOutlined />}
          onClick={() => {
            onAdd(name, "view");
            setName("");
          }}
        >
          添加为可查看
        </Button>
      </Space>
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={members}
        columns={[
          { title: "名称", dataIndex: "name" },
          {
            title: "权限",
            dataIndex: "role",
            render: (role: QaMemberRole, row) => (
              <Select
                size="small"
                value={role}
                style={{ width: 120 }}
                onChange={(v) => onRole(row.id, v)}
                options={ROLES.map((r) => ({ value: r, label: ROLE_CN[r] }))}
              />
            ),
          },
          ...(onDelete
            ? [
                {
                  title: "操作",
                  key: "actions",
                  render: (_: unknown, row: QaMember) => (
                    <Button
                      type="text"
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={() => onDelete(row.id)}
                    >
                      移除
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />
    </section>
  );
}
