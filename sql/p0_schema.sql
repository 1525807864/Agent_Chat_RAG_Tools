-- P0：会话权威库 + 用量落库（MySQL 8+ / InnoDB / utf8mb4）
-- 与 users 同库即可（langchain_demo）

CREATE TABLE IF NOT EXISTS chat_sessions (
    id              VARCHAR(191)  NOT NULL COMMENT '会话 id，含租户前缀如 default__web-xxx',
    tenant_id       VARCHAR(128)  NOT NULL DEFAULT 'default',
    title           VARCHAR(255)  NULL,
    mode            VARCHAR(32)   NOT NULL DEFAULT 'chat',
    created_at      DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_active_at  DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                  ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_sessions_tenant_active (tenant_id, last_active_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话元数据';

CREATE TABLE IF NOT EXISTS chat_messages (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    session_id   VARCHAR(191)    NOT NULL,
    tenant_id    VARCHAR(128)    NOT NULL DEFAULT 'default',
    role         VARCHAR(32)     NOT NULL COMMENT 'user|assistant|system|tool',
    content      MEDIUMTEXT      NOT NULL,
    tokens_in    INT UNSIGNED    NOT NULL DEFAULT 0,
    tokens_out   INT UNSIGNED    NOT NULL DEFAULT 0,
    model        VARCHAR(128)    NULL,
    created_at   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_msg_session_time (session_id, created_at),
    KEY idx_msg_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话消息 append-only';

CREATE TABLE IF NOT EXISTS usage_events (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id    VARCHAR(128)    NOT NULL,
    session_id   VARCHAR(191)    NULL,
    requests     INT UNSIGNED    NOT NULL DEFAULT 0,
    tokens_in    INT UNSIGNED    NOT NULL DEFAULT 0,
    tokens_out   INT UNSIGNED    NOT NULL DEFAULT 0,
    model        VARCHAR(128)    NULL,
    source       VARCHAR(32)     NOT NULL DEFAULT 'redis_flush',
    created_at   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_usage_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用量明细事件';

CREATE TABLE IF NOT EXISTS usage_daily (
    tenant_id    VARCHAR(128)    NOT NULL,
    day          DATE            NOT NULL,
    requests     BIGINT UNSIGNED NOT NULL DEFAULT 0,
    tokens_in    BIGINT UNSIGNED NOT NULL DEFAULT 0,
    tokens_out   BIGINT UNSIGNED NOT NULL DEFAULT 0,
    updated_at   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                 ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_id, day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='租户日汇总';
