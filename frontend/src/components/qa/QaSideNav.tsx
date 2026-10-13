/**
 * 左侧产品导航。选中项墨色底（主题色），栏身深色。
 */
import type { ReactNode } from "react";
import {
  ExperimentOutlined,
  FileTextOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  ReadOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Menu, Typography } from "antd";
import type { QaNav } from "../../types/qa";

const ITEMS: { id: QaNav; label: string; icon: ReactNode }[] = [
  { id: "projects", label: "项目空间", icon: <FolderOutlined /> },
  { id: "cases", label: "测试内容", icon: <ExperimentOutlined /> },
  { id: "runs", label: "执行记录", icon: <PlayCircleOutlined /> },
  { id: "report", label: "报告", icon: <FileTextOutlined /> },
  { id: "members", label: "用户与权限", icon: <TeamOutlined /> },
  { id: "knowledge", label: "知识库", icon: <ReadOutlined /> },
];

type Props = {
  nav: QaNav;
  tenantId: string;
  onChange: (nav: QaNav) => void;
};

export function QaSideNav({ nav, tenantId, onChange }: Props) {
  return (
    <nav className="qa-sidenav" aria-label="测试平台导航">
      <div className="qa-sidenav-brand">
        <Typography.Text className="qa-sidenav-brand-title">
          测试平台
        </Typography.Text>
        <Typography.Text
          className="qa-sidenav-tenant"
          ellipsis
          title={tenantId}
        >
          {tenantId}
        </Typography.Text>
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[nav]}
        className="qa-sidenav-menu"
        onClick={({ key }) => onChange(key as QaNav)}
        items={ITEMS.map((item) => ({
          key: item.id,
          icon: item.icon,
          label: item.label,
        }))}
      />
    </nav>
  );
}
