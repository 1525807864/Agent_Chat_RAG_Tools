"""config.settings — 全局配置中心（环境变量 + Pydantic Settings）

本模块职责
==========
1. 启动时 ``load_dotenv()`` 读取项目根目录 ``.env``
2. 提供模块级常量（如 ``DEEPSEEK_API_KEY``）供旧代码直接 import
3. 提供类型安全的 ``Settings`` 类与 ``get_settings()`` 单例，供
   ``AgentApplication``、记忆后端、RAG、安全限流等读取统一配置

在架构中的位置
==============
几乎所有业务模块最终都会读到这里的值；``api`` 层一般不直接读 Settings，
而是通过已初始化的 ``AgentApplication.settings`` 间接使用。

auth_backend / memory_backend
=============================
``Settings.auth_backend`` 默认 ``mysql``（登录用户表）。Docker 里 ``MYSQL_HOST``
必须是 compose 服务名 ``mysql``，不要写 ``127.0.0.1``（那是容器自己）。
本地无 MySQL 时在 ``.env`` 设 ``AUTH_BACKEND=sqlite``。

``Settings.memory_backend`` 默认 ``redis``（聊天会话）。本地若没有 Redis，
请在 ``.env`` 中显式设置 ``MEMORY_BACKEND=sqlite``。
API 依赖层（``api.deps``）**不会**自动改写该配置，以免掩盖生产误配。
"""

# 集中管理所有配置参数
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, List
import os
from dotenv import load_dotenv

# 尽早加载 .env，保证下方 os.getenv 与 Settings 都能读到同一份环境。
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE")

MODEL_NAME = "deepseek-v4-flash"
MODEL_TEMPERATURE = 0.75
MODEL_MAX_TOKENS = 2048

#搜索配置
SEARCH_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT",5))
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT",5))

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY","")
# Cursor SDK 不传 api_key 时也会读这个环境变量；空字符串表示未配置。
CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "")
CURSOR_MODEL = os.getenv("CURSOR_MODEL", "composer-2.5")
#记忆配置
MEMORY_WINDOW_SIZE = 10
#langsmith 
langsmith_tracing: bool = Field(default=False,alias="LANGSMITH_TRACING")
langsmith_api_key: str = Field(default="",alias="LANGSMITH_API_KEY")
langsmith_project: str = Field(default="nexora",alias="LANGSMITH_PROJECT")



#pydantic配置类(类型安全+自动校验)
class Settings(BaseSettings):
    """使用pydantic-settings管理所有的配置，支持.env自动加载"""
    deepseek_api_key: str = Field(
        default="",
        alias="DEEPSEEK_API_KEY",
    )
    deepseek_api_base: str = Field(
        default="https://api.deepseek.com/v1",
        alias="DEEPSEEK_API_BASE",
    )
    model_name:str = Field(
        default="deepseek-v4-flash"
    )
    model_temperature: float = Field(
        default=0.75,
        ge=0.0,
        le=2.0,
    )
    model_max_tokens:int = Field(
        default=2048,
        ge=1,
        le=1280000,
    )
    # ===== P0 鉴权 / 安全 =====
    # 本地 Electron 调试建议 false；商用 / .env 设 AUTH_ENABLED=true
    auth_enabled: bool = Field(
        default=False,
        alias="AUTH_ENABLED",
        description="启用 JWT 鉴权；false 时接口放行匿名用户",
    )
    jwt_secret: str = Field(
        default="change-me-to-long-random",
        alias="JWT_SECRET",
        description="JWT HMAC 密钥，生产必须换成长随机串",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        alias="JWT_ALGORITHM",
    )
    jwt_expire_minutes: int = Field(
        default=60 * 24,
        alias="JWT_EXPIRE_MINUTES",
        ge=1,
    )
    default_tenant_id: str = Field(
        default="default",
        alias="DEFAULT_TENANT_ID",
    )
    enable_execute_python: bool = Field(
        default=False,
        alias="ENABLE_EXECUTE_PYTHON",
        description="是否注册 execute_python 工具",
    )
    embedding_api_base: str = Field(
        default="https://api.openai.com/v1",
        alias="EMBEDDING_API_BASE",
    )
    embedding_api_key: str = Field(
        default="",
        alias="EMBEDDING_API_KEY",
    )
    # 记忆配置
    memory_window_size: int = Field(
        default=20,
        ge=1,
        le=100,
    )
    # redis | sqlite | mysql（file 预留未实现）。默认 redis；本地开发请用 .env 覆盖为 sqlite。
    memory_backend: str = Field(
        default="redis",
        alias="MEMORY_BACKEND",
        description="记忆后端类型: redis/sqlite/mysql",
    )
    # Redis 会话 key 的 TTL（秒）；SQLite 后端忽略此字段，改用 delete_old_sessions。
    memory_ttl_seconds: int = Field(
        default=3600,
        ge=60,
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
    )
    sqlite_db_path: str = Field(
        default="data/chat_history.db",
    )
    # ---- MySQL（生产用户表；Compose 内 MYSQL_HOST 必须是服务名 mysql）----
    mysql_host: str = Field(default="mysql", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT", ge=1, le=65535)
    mysql_user: str = Field(default="langchain_demo", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="langchain_demo", alias="MYSQL_DATABASE")
    # 登录用户表：生产默认 mysql；本地无库时 AUTH_BACKEND=sqlite
    auth_backend: str = Field(default="mysql", alias="AUTH_BACKEND")
    @field_validator("auth_backend")
    @classmethod
    def validate_auth_backend(cls,v:str)->str:
        raw = (v or "mysql").strip().lower()
        if raw not in {"mysql","sqlite"}:
            raise ValueError("AUTH_BACKEND 只能是 mysql 或 sqlite")
        return raw

    # ===== 四子系统记忆 / Solip =====
    memdir_path: str = Field(
        default="data/memdir",
        alias="MEMDIR_PATH",
        description="Memdir 根目录（相对项目根或绝对路径）",
    )
    memory_solip_enabled: bool = Field(
        default=True,
        alias="MEMORY_SOLIP_ENABLED",
    )
    memory_solip_top_k: int = Field(
        default=3,
        ge=1,
        le=8,
        alias="MEMORY_SOLIP_TOP_K",
    )
    memory_relevance_top_k: int = Field(
        default=6,
        ge=1,
        le=20,
        alias="MEMORY_RELEVANCE_TOP_K",
    )
    # ===== 意图追踪与任务完整性维护（Intent Guard） =====
    intent_guard_enabled: bool = Field(
        default=True,
        alias="INTENT_GUARD_ENABLED",
        description="是否启用意图守卫；false 时行为与旧版完全一致",
    )
    intent_check_model_name: str = Field(
        default="",
        alias="INTENT_CHECK_MODEL_NAME",
        description="对齐检查模型；空=与主模型相同",
    )
    intent_check_timeout_seconds: float = Field(
        default=3.0,
        ge=0.5,
        le=30.0,
        alias="INTENT_CHECK_TIMEOUT_SECONDS",
        description="单次对齐检查超时（秒），超时 fail-open 放行",
    )
    intent_check_max_per_turn: int = Field(
        default=8,
        ge=1,
        le=50,
        alias="INTENT_CHECK_MAX_PER_TURN",
        description="单回合最多执行多少次 pre-step 检查",
    )
    intent_max_tasks: int = Field(
        default=8,
        ge=1,
        le=20,
        alias="INTENT_MAX_TASKS",
        description="任务拆解的子任务上限",
    )
    intent_append_open_tasks_notice: bool = Field(
        default=True,
        alias="INTENT_APPEND_OPEN_TASKS_NOTICE",
        description="回合结束时是否在答案尾部追加【未完成任务清单】",
    )
    intent_drift_reanchor_threshold: int = Field(
        default=2,
        ge=1,
        le=5,
        alias="INTENT_DRIFT_REANCHOR_THRESHOLD",
        description="同回合连续几次 drift 判定为用户真实转向（re-anchor）",
    )
    #RAG配置
    chunk_size:int = Field(
        default=500,
        ge=100,
        le=4000
    )
    chunk_overlap:int = Field(
        default=50,
        ge=0,
        le=500
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="EMBEDDING_MODEL",
    )
    vector_db_path:str = Field(
        default="data/vector_store",
    )
    retrieval_top_k:int = Field(
        default=5,
        ge=1,
        le=20
    )
    # 混合检索 (稠密+BM25+RRF)；与 .env 的 HYBRID_RETRIEVAL_ENABLED 对齐
    hybrid_retrieval_enabled: bool = Field(
        default=True,  # 本地建议开启；出问题可设 false 回退纯向量
        alias="HYBRID_RETRIEVAL_ENABLED",
    )
    hybrid_fetch_k: int = Field(
        default=10,  # 每一路先取多少再融合，应 >= retrieval_top_k
        ge=1,
        le=50,
        alias="HYBRID_FETCH_K",
    )
    hybrid_rrf_k: int = Field(
        default=60,  # RRF 经典常数
        ge=1,
        le=200,
        alias="HYBRID_RRF_K",
    )
    hybrid_use_router: bool = Field(
        default=True,  # 是否启用 query_router；false 则永远 hybrid
        alias="HYBRID_USE_ROUTER",
    )

    # GraphRAG：图谱落盘路径、BFS 跳数、构建时抽取文本截断长度
    knowledge_graph_path: str = Field(
        default="data/knowledge_graph.json",
        alias="KNOWLEDGE_GRAPH_PATH",
    )
    graph_rag_depth: int = Field(
        default=2,
        ge=1,
        le=5,
        alias="GRAPH_RAG_DEPTH",
    )
    graph_extract_max_chars: int = Field(
        default=2000,
        ge=200,
        le=8000,
    )
    #建库时是否对每个chunk调用LLM抽三元组
    graph_extract_on_build: bool = Field(
        default=True,
        alias="GRAPH_EXTRACT_ON_BUILD",
        description="建库时是否对每个chunk调用LLM抽三元组",
    )
    # 图谱抽取最多处理多少个chunk（0=不限制，开发阶段目前测试5~20）
    graph_extract_max_docs: int = Field(
        default=0,
        alias="GRAPH_EXTRACT_MAX_DOCS",
        ge=0,
        description="图谱抽取最多处理多少个chunk（0=不限制，开发阶段目前测试5~20）",
    )

    # 路径沙箱：知识库目录 / 工具读文件必须落在这些根下（相对项目根）
    allowed_data_roots: List[str] = Field(
        default=["data"],
    )
    tool_workspace_root: str = Field(
        default="data/workspace",
    )
    #是否允许e2e打localhost,生成必须false
    e2e_allow_local: bool = Field(default=False,alias="E2E_ALLOW_LOCAL")
    e2e_root: str = Field(default="data/e2e",alias="E2E_ROOT")
    e2e_timeout_sec: int = Field(
        default=120,
        alias="E2E_TIMEOUT_SECONDS",
        ge=30,
        le=600,
    )
    e2e_user: str = Field(default="", alias="E2E_USER")
    e2e_password: str = Field(default="", alias="E2E_PASSWORD")
    # Playwright MCP：command + 逗号分隔 args（默认 npx -y @playwright/mcp@latest --headless）
    e2e_mcp_command: str = Field(default="npx", alias="E2E_MCP_COMMAND")
    e2e_mcp_args: str = Field(
        default="-y,@playwright/mcp@latest,--headless",
        alias="E2E_MCP_ARGS",
    )
    # ----------平台沙箱电脑（所有垂直agent共用执行面）
    sandbox_enabled: bool = Field(default=False,alias="SANDBOX_ENABLED")
    sandbox_runtime: str = Field(default="docker",alias="SANDBOX_RUNTIME")
    sandbox_image: str = Field(default="nexora-sandbox:latest",alias="SANDBOX_IMAGE")
    sandbox_network: str = Field(default="none",alias="SANDBOX_NETWORK")
    sandbox_memory: str = Field(default="1g",alias="SANDBOX_MEMORY")
    sandbox_cpus: int = Field(default=1,alias="SANDBOX_CPUS")
    sandbox_pids: int = Field(default=256,ge=32,le=4096,alias="SANDBOX_PIDS")
    sandbox_idle_sec: int = Field(default=1800,ge=60,le=86400,alias="SANDBOX_IDLE_SEC")
    sandbox_exec_timeout_sec: int = Field(default=60,ge=1,le=600,alias="SANDBOX_EXEC_TIMEOUT_SEC")
    sandbox_max_output_bytes: int = Field(default=65536, ge=1024, le=1_000_000, alias="SANDBOX_MAX_OUTPUT_BYTES")
    sandbox_workspace_host: str = Field(default="data/sandbox",alias="SANDBOX_WORKSPACE_HOST")
    sandbox_mode: str = Field(
        default="workspace-write",
        alias="SANDBOX_MODE",
        description="read-only | workspace-write | full-in-container",
    ) # 沙箱模式：读写工作区 | 写盘 | 全容器
    sandbox_network_mode: str = Field(
        default="deny",
        alias="SANDBOX_NETWORK_MODE",
        description="deny | allowlist | open:open内测使用",
    )
    sandbox_egress_allowlist: str = Field(
        default="",
        alias="SANDBOX_EGRESS_ALLOWLIST",
        description="逗号分隔的域名列表，如 letcode.in,example.com",
    )
    sandbox_egress_proxy_port: int = Field(
        default=18080,
        ge=1024,
        le=65535,
        alias="SANDBOX_EGRESS_PROXY_PORT",
    )
    sandbox_approval: str = Field(
        default="on-risky",
        alias="SANDBOX_APPROVAL",
        description="never | on-risky | always",
    )
    # 0 = 不限制；生产建议设 3～10
    sandbox_max_sessions_per_tenant: int = Field(
        default=3,
        ge=0,
        le=200,
        alias="SANDBOX_MAX_SESSIONS_PER_TENANT",
    )
    sandbox_allow_shell_string: bool = Field(
        default=False,
        alias="SANDBOX_ALLOW_SHELL_STRING",
        description="是否允许bash -lc 字符串（含管道符）：默认false，强制argv",
    )

    # HolmesGPT 运维引擎（旁路 HTTP，不 import holmes 源码）
    holmes_enabled: bool = Field(
        default=False,
        alias="HOLMES_ENABLED",
        description="是否启用运维排障门面（转发到 Holmes /api/chat）",
    )
    holmes_api_base: str = Field(
        default="http://127.0.0.1:5050",
        alias="HOLMES_API_BASE",
        description="Holmes HTTP 根地址，不要带尾斜杠",
    )
    # 若 Holmes 进程设置了 HOLMES_API_KEY，这里填同一把；空=不传鉴权头
    holmes_api_key: str = Field(
        default="",
        alias="HOLMES_API_KEY",
        description="调用 Holmes 时的 X-API-Key / Bearer",
    )
    # 对应 Holmes modelList 键名（如 deepseek），或 openai/deepseek-chat
    holmes_default_model: str = Field(
        default="deepseek",
        alias="HOLMES_DEFAULT_MODEL",
        description="转发给 Holmes 的 model 字段",
    )
    # 单次调查可能很久（拉日志/指标），超时要够大
    holmes_timeout_sec: float = Field(
        default=300.0,
        ge=30.0,
        le=3600.0,
        alias="HOLMES_TIMEOUT_SEC",
        description="调用 Holmes /api/chat 的超时秒数",
    )

    # ======= Ops 交互终端 (ttyd) ========
    # 总开关: false 时 /api/ops/terminal/* 一律 503
    ops_ttyd_enabled: bool = Field(
        default=False,
        alias="OPS_TTYD_ENABLED",
        description="是否启用 Ops 交互终端（ttyd）",
    )
    # ttyd 可执行文件路径；PATH 里有则写 ttyd 即可
    ops_ttyd_bin: str = Field(
        default="ttyd",
        alias="OPS_TTYD_BIN",
        description="ttyd 二进制路径",
    )
    # 只绑本机，禁止公网直连 ttyd
    ops_ttyd_bind: str = Field(
        default="127.0.0.1",
        alias="OPS_TTYD_BIND",
        description="ttyd 监听地址，必须是 127.0.0.1",
    )
    ops_ttyd_port_min: int = Field(
        default=9100, ge=1024, le=65000, alias="OPS_TTYD_PORT_MIN"
    )
    ops_ttyd_port_max: int = Field(
        default=9199, ge=1024, le=65000, alias="OPS_TTYD_PORT_MAX"
    )
    # ticket 有效期（秒）；过期需重新 POST sessions
    ops_ttyd_ticket_ttl_sec: int = Field(
        default=600, ge=60, le=3600, alias="OPS_TTYD_TICKET_TTL_SEC"
    )
    # 沙箱容器内启动的 shell
    ops_ttyd_shell: str = Field(
        default="/bin/bash",
        alias="OPS_TTYD_SHELL",
    )
    # 同一用户同时最多几个交互终端；0 = 不限制
    ops_ttyd_max_per_user: int = Field(
        default=1, ge=0, le=32, alias="OPS_TTYD_MAX_PER_USER"
    )
    # 逗号分隔 Origin（文档/校验用）；ttyd 的 -O 是布尔开关，不接收列表参数
    ops_ttyd_allowed_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="OPS_TTYD_ALLOWED_ORIGINS",
    )
    # P3：禁止开「可写」终端的 user_id 列表（逗号分隔）；只读不受影响
    ops_ttyd_deny_users: str = Field(
        default="",
        alias="OPS_TTYD_DENY_USERS",
        description="禁止可写交互终端的用户 id，逗号分隔",
    )
    # P4：用 script 录制终端 typescript 到 /workspace/.nexora/
    ops_ttyd_recording_enabled: bool = Field(
        default=True,
        alias="OPS_TTYD_RECORDING_ENABLED",
        description="是否用 script 录制交互终端会话",
    )
    # native=本机直接跑 ttyd；wsl=经 wsl.exe 在 Linux 里跑（Windows 开发机想打字就用这个）
    ops_ttyd_runtime: str = Field(
        default="native",
        alias="OPS_TTYD_RUNTIME",
        description="ttyd 怎么起：native 或 wsl",
    )
    # 填 wsl -l -v 里那一列名字；空着就用默认发行版
    ops_ttyd_wsl_distro: str = Field(
        default="",
        alias="OPS_TTYD_WSL_DISTRO",
        description="WSL 发行版名，空=默认",
    )
    # 一般写 wsl 就行，PATH 里有
    ops_ttyd_wsl_exe: str = Field(
        default="wsl",
        alias="OPS_TTYD_WSL_EXE",
        description="wsl.exe 路径",
    )
    #搜索配置
    tavily_api_key:str = Field(
        default="",
        alias="TAVILY_API_KEY",
        description="Tavily Search API Key:空则web_search会提示未配置",
    )
    # Cursor Agent SDK。改代码的 chat/agent 会分配到这里；RAG 仍走 DeepSeek。
    cursor_api_key: str = Field(
        default="",
        alias="CURSOR_API_KEY",
        description="Cursor 用户密钥或 Service account；Team Admin key 不可用",
    )
    cursor_model: str = Field(
        default="composer-2.5",
        alias="CURSOR_MODEL",
        description="本地 Agent 必填模型；composer-2.5 或 auto",
    )
    # 通用 MCP：JSON 数组字符串。空 = 本轮不拉外部 MCP。
    mcp_servers_json: str = Field(
        default="",
        alias="MCP_SERVERS_JSON",
        description='例: [{"name":"playwright","command":"npx","args":["-y","@playwright/mcp@latest","--headless"]}]',
    )
    # 主动工具发现：true 时 Agent 不全量注入工具 schema
    active_tool_discovery: bool = Field(
        default=False,
        alias="ACTIVE_TOOL_DISCOVERY",
    )
    active_tool_top_k: int = Field(
        default=5,
        alias="ACTIVE_TOOL_TOP_K",
        ge=1,
        le=20,
    )
    # 逗号分隔的常驻工具名
    active_tool_base: str = Field(
        default="calculator,web_search",
        alias="ACTIVE_TOOL_BASE",
    )
    search_result_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        alias="SEARCH_RESULT_LIMIT",
    )
    search_timeout: int = Field(
        default=10,
        ge=1,
        le=60,
        alias="SEARCH_TIMEOUT",
    )
    # 部分网络/杀软会劫持 HTTPS，导致 Tavily 报 SSL EOF；可在 .env 设 SEARCH_SSL_VERIFY=false
    search_ssl_verify: bool = Field(
        default=True,
        alias="SEARCH_SSL_VERIFY",
    )
    #代理配置
    max_agent_iterations:int = Field(
        default=15,
        ge=1,
        le=100
    )#Agent最大迭代次数
    max_tool_calls_per_turn:int = Field(
        default=5,
        ge=1,
        le=20
    )
    # 速率限制
    rate_limit_requests: int = Field(default=60, ge=1)
    # 每分钟最多请求数
    rate_limit_tokens: int = Field(default=100000, ge=1)
    # 每分钟最多 Token 数

    #========== 生产相关配置 ==========
    # 是否暴露 /docs /redoc /openapi.json；生产建议 false
    openapi_enabled: bool = Field(
        default=True,  # 本地开发默认开文档
        alias="OPENAPI_ENABLED",
        description="false 时不挂载 Swagger/ReDoc",
    )
    #是否允许调试发token路由,生产必须false
    auth_debug_enabled: bool = Field(
        default=True, #本地方便联调
        alias="AUTH_DEBUG_ENABLED",
        description="false时不注册 /api/auth/dev-token 路由"
    )
    #CORS白名单，逗号分隔的Origin列表字符串
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,null",
        alias="CORS_ORIGINS",
        description="浏览器允许的Origin,逗号分隔",
    )
    admin_username: str = Field(
        default="admin",
        alias="ADMIN_USERNAME",
    )
    admin_password: str = Field(
        default="admin123456",
        alias="ADMIN_PASSWORD",
        description="仅用于空库引导管理员；生产必须改掉默认值",
    )
    auth_users_db_path: str = Field(
        default="data/users.db",
        alias="AUTH_USERS_DB_PATH",
        description="用户表 SQLite 路径（相对项目根或绝对路径）",
    )
    auth_bootstrap_reset_admin: bool = Field(
        default=False,
        alias="AUTH_BOOTSTRAP_RESET_ADMIN",
        description="true 时每次启动用 ADMIN_PASSWORD 覆盖管理员哈希",
    )
    allow_register: bool = Field(
        default=False,
        alias="ALLOW_REGISTER",
        description="是否开放 POST /api/auth/register",
    )
    desktop_download_enabled: bool = Field(
        default=True,
        alias="DESKTOP_DOWNLOAD_ENABLED",
        description="是否开放 GET /api/downloads/desktop",
    )
    desktop_release_dir: str = Field(
        default="downloads",
        alias="DESKTOP_RELEASE_DIR",
        description="安装包目录，相对项目根或绝对路径。把 Nexora-Setup.exe 放这里",
    )
    desktop_release_name: str = Field(
        default="Nexora-Setup.exe",
        alias="DESKTOP_RELEASE_NAME",
        description="目录内的安装包文件名，只允许单层 .exe 名",
    )
    desktop_release_max_bytes: int = Field(
        default=800 * 1024 * 1024,
        alias="DESKTOP_RELEASE_MAX_BYTES",
        ge=1,
        description="安装包大小上限，超过则拒绝下载",
    )
    desktop_download_rate_limit: int = Field(
        default=20,
        alias="DESKTOP_DOWNLOAD_RATE_LIMIT",
        ge=1,
        le=120,
        description="同一 IP 每分钟最多下载次数（含 meta 查询分开计数）",
    )
    strict_production: bool = Field(
        default=False,
        alias="STRICT_PRODUCTION",
        description="true 时拒绝弱配置启动（调试路由、默认密码、内存限流等）",
    )
    trust_proxy: bool = Field(
        default=False,
        alias="TRUST_PROXY",
        description="true 时信任 X-Real-IP / X-Forwarded-For（仅 Nginx 后启用）",
    )
    rate_limit_backend: str = Field(
        default="memory",
        alias="RATE_LIMIT_BACKEND",
        description="memory | redis；生产请用 redis",
    )
    login_rate_limit: int = Field(
        default=5,
        alias="LOGIN_RATE_LIMIT",
        ge=1,
        le=60,
        description="同一 IP 每分钟最多登录尝试次数",
    )
    allowed_hosts: str = Field(
        default="*",
        alias="ALLOWED_HOSTS",
        description="TrustedHost 白名单，逗号分隔；* 表示不启用",
    )
    # 总开关:false时行为与旧版一致，便于回滚
    memory_v2_enabled: bool = Field(
        default=True,
        alias="MEMORY_V2_ENABLED",
        description="启用查询改写/槽位/语义记忆抽取与混合召回",
    )
    # 短句指代补全（「今天有雨吗」→「北京今天有雨吗」）
    memory_query_rewrite_enabled: bool = Field(
        default=True,
        alias="MEMORY_QUERY_REWRITE_ENABLED",
        description="Memory V2：短句/省略主语查询改写",
    )
    # 每轮结束后抽取可复用事实
    memory_fact_extract_enabled: bool = Field(
        default=True,
        alias="MEMORY_FACT_EXTRACT_ENABLED",
    )
    # 语义召回 top_k
    memory_semantic_top_k: int = Field(default=6, ge=1, le=20)
    # 摘要最大 token
    memory_summary_max_tokens: int = Field(default=480, ge=100, le=2000)
    # 压缩触发：消息条数 / token 阈值
    memory_compress_min_messages: int = Field(default=12, ge=4, le=100)
    memory_compress_max_context_tokens: int = Field(default=3500, ge=1000)
    # 语义记忆落盘根（按 tenant 分子目录）
    memory_semantic_path: str = Field(
        default="data/memory_semantic",
        alias="MEMORY_SEMANTIC_PATH",
    )
    langsmith_tracing: bool = Field(
        default=False,
        alias="LANGSMITH_TRACING",
        description="是否向 LangSmith 上报；无密钥时启动会 fail-open",
    )
    langsmith_api_key: str = Field(
        default="",
        alias="LANGSMITH_API_KEY",
        description="LangSmith API Key（lsv2_ 开头）；不要提交到仓库",
    )
    langsmith_project: str = Field(
        default="nexora",
        alias="LANGSMITH_PROJECT",
        description="LangSmith 项目名，开发/生产请分开",
    )
    langsmith_endpoint: str = Field(
        default="",
        alias="LANGSMITH_ENDPOINT",
        description="留空用官方默认；不要写成本机 FastAPI 的 LANGCHAIN_API_BASE",
    )


    # 安全
    allowed_tool_patterns: List[str] =Field(default=["*"])  # 允许的工具白名单
    blocked_keywords: List[str] = Field(default=[])# 敏感词过滤
    #调试
    debug:bool = Field(
        default=True,
    )
    log_level:str = Field(
        default="INFO",
    )
    @field_validator("memory_backend")
    @classmethod
    def validate_memory_backend(cls,v:str)->str:
        # 校验白名单，防止拼错静默落到错误实现
        raw = (v or "redis").strip().lower()
        if raw not in {"redis","sqlite","mysql"}:
            raise ValueError("MEMORY_BACKEND 只能是 redis/sqlite/mysql")
        return raw

    @field_validator("rate_limit_backend")
    @classmethod
    def validate_rate_limit_backend(cls, v: str) -> str:
        raw = (v or "memory").strip().lower()
        if raw not in {"memory", "redis"}:
            raise ValueError("RATE_LIMIT_BACKEND 只能是 memory 或 redis")
        return raw

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v:str)->str:
        valid = {"DEBUG","INFO","WARNING","ERROR","CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid:
            raise ValueError(f"Invalid log level: {v}")
        return v_upper
    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "protected_namespaces": ("settings_",),
        "populate_by_name": True,
    }

    @field_validator("sandbox_runtime")
    @classmethod
    def validate_sandbox_runtime(cls,v:str)->str:
        raw = (v or "docker").strip().lower()
        if raw not in {"docker"}:
            raise ValueError("SANDBOX_RUNTIME 目前只支持 docker")
        return raw
    def cors_origin_list(self)->list[str]:
        #把CORS_ORIGINS拆成list，供Fastapi CORSMiddleware使用
        parts = (self.cors_origins or "").split(",")
        return [p.strip() for p in parts if p.strip()] #去掉空白，丢掉字段
    
    @field_validator("sandbox_mode")
    @classmethod
    def validate_sandbox_mode(cls,v:str)->str:
        raw = (v or "workspace-write").strip().lower()
        if raw not in {"read-only","workspace-write","full-in-container"}:
            raise ValueError("SANDBOX_MODE 只能是 read-only/workspace-write/full-in-container")
        return raw 
    @field_validator("sandbox_network_mode")
    @classmethod 
    def validate_sandbox_network_mode(cls,v:str)->str:
        raw = (v or "deny").strip().lower()
        if raw not in {"deny","allowlist","open"}:
            raise ValueError("SANDBOX_NETWORK_MODE 只能是 deny/allowlist/open")
        return raw 
    @field_validator("sandbox_approval")
    @classmethod 
    def validate_sandbox_approval(cls,v:str)->str:
        raw = (v or "on-risky").strip().lower()
        if raw not in {"never","on-risky","always"}:
            raise ValueError("SANDBOX_APPROVAL 只能是 never/on-risky/always")
        return raw 
    #配置extar:ignore忽略.env里里面的未知字段，不会因为多余的配置导致程序无法运行
# 全局单例：避免重复解析 .env / 构造 Settings。
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """延迟初始化 Settings，确保 ``load_dotenv()`` 已执行后再读环境变量。

    返回同一进程内共享的 Settings 实例；测试若需隔离，可重置模块级 ``_settings``。
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def validate_config():
    """启动前快速校验：至少要有 DeepSeek API Key（模块级常量视角）。

    与 Settings.deepseek_api_key 可能略有差异（Settings 允许空字符串默认值）；
    CLI 若需严格失败，可在入口调用本函数。
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY环境变量没有设置")
    return True
