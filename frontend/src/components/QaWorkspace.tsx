/**
 * 测试平台壳：左导航 + 中间页 + 右侧助手。
 * 未选项目时中间是项目列表；选中后可切到用例 / 记录 / 报告。
 */
import type { ReactNode } from "react";
import { Alert, Button, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { KnowledgePanel } from "./KnowledgePanel";
import { useQaShell } from "../hooks/useQaShell";
import { QaProjectList } from "./qa/QaProjectList";
import { QaSideNav } from "./qa/QaSideNav";
import { QaAssistant } from "./qa/QaAssistant";
import { QaCaseTree } from "./qa/QaCaseTree";
import { QaCaseDetail } from "./qa/QaCaseDetail";
import { QaRunsPage } from "./qa/QaRunsPage";
import { QaReportPage } from "./qa/QaReportPage";
import { QaMembersPage } from "./qa/QaMembersPage";
import type { QaNav } from "../types/qa";

export function QaWorkspace() {
  const shell = useQaShell();

  const onNav = (nav: QaNav) => {
    if (nav === "projects") {
      shell.backToList();
      return;
    }
    shell.setNav(nav);
  };

  let center: ReactNode;
  if (shell.nav === "projects" || !shell.activeProject) {
    center = (
      <QaProjectList
        projects={shell.projects}
        busy={shell.busy}
        onOpen={shell.openProject}
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
        />
        <QaCaseDetail
          project={shell.activeProject}
          selected={shell.selectedCase}
          busy={shell.busy}
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
        busy={shell.busy}
        onSmoke={() => void shell.runSmoke()}
      />
    );
  } else if (shell.nav === "report") {
    center = <QaReportPage runs={shell.runs} cases={shell.cases} />;
  } else if (shell.nav === "members") {
    center = (
      <QaMembersPage
        tenantId={shell.tenantId}
        members={shell.members}
        onAdd={shell.addMember}
        onRole={shell.setMemberRole}
      />
    );
  } else {
    center = (
      <div className="qa-pane qa-center-page">
        <KnowledgePanel />
      </div>
    );
  }

  return (
    <div className="qa-app">
      <QaSideNav nav={shell.nav} tenantId={shell.tenantId} onChange={onNav} />
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
        onToggleMaterials={() => shell.setMaterialsOpen(!shell.materialsOpen)}
        onSend={(text) => void shell.sendAssistant(text)}
        onUpload={(file) => void shell.addLocalSource(file)}
        onSaveEnv={(patch) => void shell.saveProject(patch)}
      />
    </div>
  );
}
