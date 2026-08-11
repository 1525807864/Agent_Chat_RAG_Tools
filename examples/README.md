# 示例与废弃入口

本目录存放**不再作为主入口**的演示脚本，仅供对照学习。

| 文件 | 说明 |
|------|------|
| `legacy_chat_demo.py` | 早期内存会话聊天（原根目录 `app.py`），已由 `python main.py` / FastAPI 取代 |
| `application_demo_deprecated.py` | 早期 LCEL 试验脚本（原 `application_Demo.py`），依赖旧写法，勿用于生产 |

正式入口：

- CLI：`python main.py`
- API：`uvicorn api.server:app --reload --port 8000`
