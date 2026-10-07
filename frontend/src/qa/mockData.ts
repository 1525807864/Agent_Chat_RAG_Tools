/**
 * mockData.ts
 * 首次进入测试工作台时的种子数据（仿万象示例项目）。
 * 纯前端演示用；接后端后可删掉 createSeed*。
 */
import type { QaCase, QaProject, QaSourceDoc } from "../types/qa";

/** 生成短 id（浏览器端够用） */
export function qaId(prefix = "qa"): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

/** 示例来源文档 */
export function createSeedSources(): QaSourceDoc[] {
  return [
    {
      id: "src-srs",
      name: "卫星导航系统软件需求规格说明.docx",
      kind: "docx",
      excerpt:
        "SRS-1 初始化功能：系统启动后完成基带引擎、射频芯片与星历装订的初始化流程，参与者为操作员与监控终端。",
      rows: [
        {
          no: "1",
          name: "初始化功能",
          reqId: "SRS-1",
          description: "上电后完成模块自检与参数装订",
        },
        {
          no: "2",
          name: "定位参数配置",
          reqId: "SRS-3",
          description: "配置定位解算相关参数并校验范围",
        },
      ],
    },
    {
      id: "src-task",
      name: "导航系统软件研制任务书.docx",
      kind: "docx",
      excerpt:
        "任务书要求：初始化阶段须在规定时限内完成，失败时给出可诊断告警，不得静默失败。",
      rows: [
        {
          no: "1",
          name: "时限与告警",
          reqId: "TSK-01",
          description: "初始化超时须告警并可追溯日志",
        },
      ],
    },
  ];
}

/** 示例项目 */
export function createSeedProject(): QaProject {
  return {
    id: "proj-demo",
    name: "测试项生成示例项目",
    baseUrl: "https://www.example.com",
    goal: "围绕初始化与接口探活生成可确认的测试内容树",
    createdAt: new Date().toISOString(),
    sourceDocs: createSeedSources(),
  };
}

/** 示例用例树（根 + 若干子项） */
export function createSeedCases(projectId: string): QaCase[] {
  const rootId = "case-root";
  return [
    {
      id: rootId,
      projectId,
      parentId: null,
      code: "4.1",
      title: "初始化功能",
      kind: "functional",
      requirement:
        "系统启动后完成基带引擎、射频芯片与星历装订的初始化；失败需告警。",
      fused:
        "验证上电初始化主路径：模块自检 → 参数装订 → 状态上报；异常路径须可见告警。",
      steps: ["上电/打开被测入口", "观察初始化进度", "确认状态与告警"],
      expected: "初始化成功或失败原因可见",
      status: "confirmed",
      sourceDocIds: ["src-srs", "src-task"],
    },
    {
      id: "case-fn",
      projectId,
      parentId: rootId,
      code: "4.1.1",
      title: "初始化主路径",
      kind: "functional",
      requirement: "正常参数下完成初始化",
      fused: "使用默认配置走通初始化，检查关键状态文案。",
      steps: ["进入初始化", "等待完成", "核对状态"],
      expected: "状态为就绪且无阻断错误",
      status: "draft",
      sourceDocIds: ["src-srs"],
    },
    {
      id: "case-sec",
      projectId,
      parentId: rootId,
      code: "4.1.2",
      title: "初始化失败告警",
      kind: "security",
      requirement: "失败不得静默",
      fused: "注入失败条件，确认告警与日志字段。",
      steps: ["制造失败条件", "观察告警", "检查日志"],
      expected: "告警可见且可追溯",
      status: "draft",
      sourceDocIds: ["src-task"],
    },
    {
      id: "case-api",
      projectId,
      parentId: rootId,
      code: "4.1.3",
      title: "接口探活",
      kind: "api",
      requirement: "对 Base URL 做可达性检查",
      fused: "对项目 Base URL 发起 GET，状态码 < 500 视为探活通过（壳阶段为模拟）。",
      steps: ["读取 Base URL", "模拟 GET", "记录结果"],
      expected: "记录 pass/fail 与摘要",
      status: "draft",
      sourceDocIds: [],
    },
    {
      id: "case-perf",
      projectId,
      parentId: rootId,
      code: "4.1.4",
      title: "资源消耗占位",
      kind: "performance",
      requirement: "预留性能 SLO",
      fused: "壳阶段仅占位：后续接 k6 填 p95 阈值。",
      steps: ["填写 SLO", "待执行器接入"],
      expected: "SLO 字段已确认",
      status: "draft",
      sourceDocIds: [],
    },
  ];
}