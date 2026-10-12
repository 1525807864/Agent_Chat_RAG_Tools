// ============================================================================
// 全局审批队列：任意 API/Agent 调用 requestApproval() 即可弹出底部卡片
// 单例模块，不依赖 React Context，Sheet 组件订阅即可
// ============================================================================

import type {
    PendingSandboxApproval, // 带 resolve 的挂起项
    SandboxApprovalRequest, // 业务传入的审批载荷
  } from "./types";
  
  /** 当前排队中的审批（同时只展示队首，避免叠两张卡） */
  let queue: PendingSandboxApproval[] = [];
  
  /** 监听者列表：Sheet 挂载时 subscribe，卸载时退订 */
  const listeners = new Set<() => void>();
  
  /** 通知所有订阅者「队列变了，请重绘」 */
  function emit(): void {
    // 遍历复制一份，防止订阅方在回调里退订导致迭代异常
    for (const fn of [...listeners]) {
      // 调用监听函数
      fn();
    }
  }
  
  /**
   * 请求用户确认。返回 Promise<boolean>。
   * true  = 允许并应重放请求；false = 拒绝。
   */
  export function requestApproval(
    req: SandboxApprovalRequest, // 会话、命令、风险文案
  ): Promise<boolean> {
    // 返回一个由用户点击 resolve 的 Promise
    return new Promise<boolean>((resolve) => {
      // 把业务载荷与 resolve 捆成挂起项
      const item: PendingSandboxApproval = {
        ...req, // 展开 sessionId/kind/argv/risk...
        resolve, // 保存 Promise 的 resolve
      };
      // 入队尾
      queue = [...queue, item];
      // 通知 UI
      emit();
    });
  }
  
  /** 当前应展示的队首审批；无则 null */
  export function getCurrentApproval(): PendingSandboxApproval | null {
    // 队首或空
    return queue[0] ?? null;
  }
  
  /** 用户点允许或拒绝时调用 */
  export function settleApproval(allowed: boolean): void {
    // 取出队首
    const head = queue[0];
    // 没有挂起项则直接返回
    if (!head) return;
    // 先出队，避免重入
    queue = queue.slice(1);
    // 兑现 Promise
    head.resolve(allowed);
    // 若还有下一项，Sheet 会自动展示下一条
    emit();
  }
  
  /** React 组件订阅队列变化 */
  export function subscribeApproval(listener: () => void): () => void {
    // 加入订阅集合
    listeners.add(listener);
    // 返回退订函数给 useEffect cleanup
    return () => {
      // 从集合删除
      listeners.delete(listener);
    };
  }