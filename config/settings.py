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
    # redis | sqlite（file 预留未实现）。默认 redis；本地开发请用 .env 覆盖为 sqlite。
    memory_backend: str = Field(
        default="redis",
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


    def cors_origin_list(self)->list[str]:
        #把CORS_ORIGINS拆成list，供Fastapi CORSMiddleware使用
        parts = (self.cors_origins or "").split(",")
        return [p.strip() for p in parts if p.strip()] #去掉空白，丢掉字段
        

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
