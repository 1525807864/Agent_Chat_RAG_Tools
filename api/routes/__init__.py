"""api.routes 包 — 按业务域拆分的 FastAPI 路由模块

本包内各模块通过 ``APIRouter`` 定义端点，再由 ``api.server`` 统一 ``include_router``。

模块一览
========
- ``chat``      ：``POST /api/chat``、``POST /api/chat/stream``（对话与 SSE 占位流）
- ``sessions``  ：会话列表 / 历史查询 / 删除
- ``knowledge`` ：知识库构建、知识图谱统计

拆分原因：路由文件随接口增多会迅速膨胀；按域拆分后，改聊天不影响知识库路由，
也便于给不同 ``tags`` 生成 OpenAPI 分组文档。
"""
