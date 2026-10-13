/**
 * 测试平台壳：左导航 + 中间页 + 右侧助手。
 * 未选项目时中间是项目列表；选中后可切到用例 / 记录 / 报告。
 * 按钮按 /api/qa/me 返回的 permissions 禁用（安全边界仍在后端）。
 */
import type { ReactNode } from "react";
import { Alert, Button, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useQaShell } from "../hooks/useQaShell";
import { SandboxApprovalSheet } from "./sandbox/SandboxApprovalSheet";
import "../styles/sandbox-approval.css";
import { QaProjectList } from "./qa/QaProjectList";
import { QaSideNav } from "./qa/QaSideNav";
import { QaAssistant } from "./qa/QaAssistant";
import { QaCaseTree } from "./qa/QaCaseTree";
import { QaCaseDetail } from "./qa/QaCaseDetail";
import { QaRunsPage } from "./qa/QaRunsPage";
import { QaReportPage } from "./qa/QaReportPage";
import { QaMembersPage } from "./qa/QaMembersPage";
import { QaKnowledgePage } from "./qa/QaKnowledgePage";


export function QaWorkspace() {
  const shell = useQaShell();
  const perms = shell.permissions;

  let center: ReactNode;
  if (shell.nav === "projects" || !shell.activeProject) {
    center = (
      <QaProjectList
        projects={shell.projects}
        busy={shell.busy}
        canWrite={perms.canWriteProject}
        onOpen={(id) => void shell.openProject(id)}
        onCreate={(name, baseUrl, goal) => {
          void shell.createProject(name, baseUrl, goal);
        }}
        onResetDemo={shell.resetDemo}
        onDelete={(id) => void shell.deleteProject(id)}
      />
    );
  } else if (shell.nav === "cases") {
    center = (
      <div className="qa-cases-split">
        <QaCaseTree
          cases={shell.cases}
          selectedId={shell.selectedCaseId}
          query={shell.treeQuery}
          onQuery={shell.setTreeQuery}
          onSelect={shell.setSelectedCaseId}
          onGenerate={() => void shell.generateCases()}
          onDelete={(id) => void shell.deleteCase(id)}
          busy={shell.busy}
          canWrite={perms.canWriteCase}
        />
        <QaCaseDetail
          project={shell.activeProject}
          selected={shell.selectedCase}
          busy={shell.busy}
          canWrite={perms.canWriteCase}
          onConfirm={(fused) => void shell.confirmCase(fused)}
          onGenerate={() => void shell.generateCases()}
          onDelete={(id) => void shell.deleteCase(id)}
        />
      </div>
    );
  } else if (shell.nav === "runs") {
    center = (
      <QaRunsPage
        runs={shell.runs}
        defaultUrl={shell.activeProject.baseUrl}
        busy={shell.busy}
        uiRunning={shell.uiRunning}
        canExecute={perms.canExecute}
        onSmoke={() => void shell.runSmoke()}
        onUi={(name, url, goal) => void shell.runUi(name, url, goal)}
        onExport={(runId, fmt) => void shell.exportRun(runId, fmt)}
      />
    );
  } else if (shell.nav === "report") {
    center = (
      <QaReportPage
        runs={shell.runs}
        cases={shell.cases}
        projectName={shell.activeProject.name}
      />
    );
  } else if (shell.nav === "members") {
    center = (
      <QaMembersPage
        tenantId={shell.tenantId}
        members={shell.members}
        canManage={perms.canManageMembers}
        onInvite={(body) => void shell.inviteMember(body)}
        onRole={(id, role) => void shell.setMemberRole(id, role)}
        onDelete={(id) => void shell.deleteMember(id)}
      />
    );
  } else {
    center = (
      <QaKnowledgePage
        project={shell.activeProject}
        busy={shell.busy}
        canWrite={perms.canWriteProject}
        onUpload={(f) => void shell.addLocalSource(f)}
      />
    );
  }

  return (
    <div className="qa-app">
      <QaSideNav
        nav={shell.nav}
        tenantId={shell.tenantId}
        onChange={shell.setNav}
      />
      <div className="qa-main">
        {shell.activeProject && shell.nav !== "projects" ? (
          <div className="qa-subhead">
            <Button
              type="link"
              icon={<ArrowLeftOutlined />}
              onClick={shell.backToList}
            >
              返回项目列表
            </Button>
            <Typography.Text strong className="qa-subhead-title">
              {shell.activeProject.name}
            </Typography.Text>
          </div>
        ) : null}
        {shell.notice ? (
          <Alert
            type="info"
            showIcon
            message={shell.notice}
            className="qa-notice-alert"
          />
        ) : null}
        <div className="qa-main-body">{center}</div>
      </div>
      <QaAssistant
        project={shell.activeProject}
        chat={shell.chat}
        runs={shell.runs}
        busy={shell.busy}
        materialsOpen={shell.materialsOpen}
        canWriteCase={perms.canWriteCase}
        canWriteProject={perms.canWriteProject}
        onToggleMaterials={() => shell.setMaterialsOpen(!shell.materialsOpen)}
        onSend={(text) => void shell.sendAssistant(text)}
        onUpload={(file) => void shell.addLocalSource(file)}
        onSaveEnv={(patch) => void shell.saveProject(patch)}
        uiSteps={shell.uiSteps}
        uiRunning={shell.uiRunning}
      />
      {/* 全局沙箱高危确认：与侧栏/主区平级，勿再包一层 qa-app */}
      <SandboxApprovalSheet />
    </div>
  );
}
