"""平台沙箱电脑：隔离执行面，供全部垂直 Agent 使用。

垂直业务（QA / 运维 / 办公）只通过 Broker 申请会话与执行命令，
禁止直接 docker exec 宿主机。
"""

from infrastructure.sandbox.broker import SandboxBroker, get_sandbox_broker

__all__ = ["SandboxBroker", "get_sandbox_broker"]
