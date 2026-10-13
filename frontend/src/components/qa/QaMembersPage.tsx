/**
 * 测试平台「用户与权限」：仅 admin 可邀请本租户登录账号并指定角色。
 * execute / view 进来应传 canManage=false，表格只读。
 */
import { useState } from "react";
import { Button, Input, Select, Space, Table, Typography } from "antd";
import { DeleteOutlined, UserAddOutlined } from "@ant-design/icons";
import type { QaMember, QaMemberRole } from "../../types/qa";

const ROLES: QaMemberRole[] = ["admin", "execute", "view"];
const ROLE_CN: Record<QaMemberRole, string> = {
  admin: "可管理（改用例 / 管成员）",
  execute: "可执行（不能改用例）",
  view: "只读",
};

export function QaMembersPage({
  tenantId,
  members,
  canManage,
  onInvite,
  onRole,
  onDelete,
}: {
  tenantId: string;
  members: QaMember[];
  canManage: boolean;
  onInvite: (body: {
    username: string;
    password: string;
    role: QaMemberRole;
    name: string;
  }) => void;
  onRole: (id: string, role: QaMemberRole) => void;
  onDelete?: (id: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<QaMemberRole>("view");

  return (
    <section className="qa-pane qa-center-page">
      <div className="qa-pane-head">
        <span>
          用户与权限 ·{" "}
          <Typography.Text type="secondary">{tenantId}</Typography.Text>
        </span>
      </div>
      <Typography.Paragraph type="secondary">
        第一个进入本租户测试台的用户自动成为管理员。管理员可给团队开通登录账号，并指定
        admin / execute / view。execute 只能跑用例，不能改用例。
      </Typography.Paragraph>
      {canManage ? (
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            style={{ width: 160 }}
            value={username}
            placeholder="登录用户名"
            onChange={(e) => setUsername(e.target.value)}
          />
          <Input.Password
            style={{ width: 160 }}
            value={password}
            placeholder="初始密码（≥8）"
            onChange={(e) => setPassword(e.target.value)}
          />
          <Input
            style={{ width: 140 }}
            value={name}
            placeholder="展示名（可选）"
            onChange={(e) => setName(e.target.value)}
          />
          <Select
            style={{ width: 220 }}
            value={role}
            onChange={setRole}
            options={ROLES.map((r) => ({ value: r, label: ROLE_CN[r] }))}
          />
          <Button
            type="primary"
            icon={<UserAddOutlined />}
            onClick={() => {
              onInvite({ username, password, role, name });
              setUsername("");
              setPassword("");
              setName("");
              setRole("view");
            }}
          >
            邀请加入本租户
          </Button>
        </Space>
      ) : (
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
          你没有管理成员的权限。
        </Typography.Text>
      )}
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={members}
        columns={[
          { title: "登录账号", dataIndex: "userId" },
          { title: "展示名", dataIndex: "name" },
          {
            title: "角色",
            dataIndex: "role",
            render: (r: QaMemberRole, row) =>
              canManage ? (
                <Select
                  size="small"
                  value={r}
                  style={{ width: 220 }}
                  onChange={(v) => onRole(row.id, v)}
                  options={ROLES.map((x) => ({ value: x, label: ROLE_CN[x] }))}
                />
              ) : (
                ROLE_CN[r]
              ),
          },
          ...(canManage && onDelete
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
