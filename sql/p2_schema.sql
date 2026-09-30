-- P2：精选记忆索引 + transcript 归档指针

CREATE TABLE IF NOT EXISTS memory_items (
    id            VARCHAR(64)   NOT NULL,
    tenant_id     VARCHAR(128)  NOT NULL,
    session_id    VARCHAR(191)  NULL COMMENT 'NULL=项目级',
    kind          VARCHAR(32)   NOT NULL,
    text          TEXT          NOT NULL,
    origin        VARCHAR(32)   NOT NULL DEFAULT 'agent'
                  COMMENT 'user|agent|tool_web|system',
    tags_json     JSON          NULL,
    meta_json     JSON          NULL,
    score_hint    FLOAT         NOT NULL DEFAULT 0.5,
    created_at    DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                  ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_mem_tenant_session (tenant_id, session_id),
    KEY idx_mem_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transcript_archives (
    session_id    VARCHAR(191)  NOT NULL,
    tenant_id     VARCHAR(128)  NOT NULL,
    storage_uri   VARCHAR(1024) NOT NULL COMMENT 'file://... 或 s3://...',
    bytes         BIGINT        NOT NULL DEFAULT 0,
    created_at    DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
