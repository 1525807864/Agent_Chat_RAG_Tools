// 沙箱高危命令审批：前后端共用的前端类型
// 触发审批的命令类型（对应后端ExecKind/路由）
export type SandboxApprovalKind = "shell" | "pwsh" | "exec";
/**
 * 一次待确认的高危操作。
 * resolve(true)  = 用户点「仅本次允许」→ API 带 approved:true 重放
 * resolve(false) = 用户点「拒绝」→ 调用方抛错或写 cancelled
 */
export type SandboxApprovalRequest = {
    /** 沙箱会话 id（后端 session id） */
    sessionId: string;
    /** 命令类型：shell / pwsh / 文件工具 */
    kind: SandboxApprovalKind;
    /** 命令参数：shell 时有效 */
    argv?:string[];
    /** 命令字符串：shell 时有效 */
    command?:string;
    /** 风险提示：human readable */
    risk: string;
    /** 垂直名称：对应后端 vertical */
    vertical?:string;
};
// store里挂起的请求：带Promise回调
export type PendingSandboxApproval = SandboxApprovalRequest & {
    // 回调：允许/拒绝
    resolve: (allowed: boolean) => void;
};