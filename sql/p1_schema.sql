-- P1：Agent 运行审计、路由、咨询因子、KB Job

CREATE TABLE IF NOT EXISTS agent_runs (
    id             VARCHAR(64)   NOT NULL,
    tenant_id      VARCHAR(128)  NOT NULL,
    session_id     VARCHAR(191)  NOT NULL,
    mode           VARCHAR(32)   NOT NULL DEFAULT 'agent',
    model          VARCHAR(128)  NULL,
    status         VARCHAR(32)   NOT NULL DEFAULT 'ok',
    answer_preview VARCHAR(512)  NULL,
    tokens_in      INT UNSIGNED  NOT NULL DEFAULT 0,
    tokens_out     INT UNSIGNED  NOT NULL DEFAULT 0,
    latency_ms     INT UNSIGNED  NOT NULL DEFAULT 0,
    error_message  VARCHAR(1024) NULL,
    created_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_runs_session (session_id, created_at DESC),
    KEY idx_runs_tenant (tenant_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tool_invocations (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id         VARCHAR(64)   NOT NULL,
    tenant_id      VARCHAR(128)  NOT NULL,
    session_id     VARCHAR(191)  NOT NULL,
    tool_name      VARCHAR(128)  NOT NULL,
    input_json     JSON          NULL,
    output_preview VARCHAR(2000) NULL,
    forced         TINYINT(1)    NOT NULL DEFAULT 0,
    created_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_tool_run (run_id),
    KEY idx_tool_session (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS session_routing (
    tenant_id      VARCHAR(128)  NOT NULL,
    session_id     VARCHAR(191)  NOT NULL,
    provider       VARCHAR(32)   NOT NULL DEFAULT 'cursor',
    agent_id       VARCHAR(191)  NOT NULL DEFAULT '',
    updated_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                   ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_id, session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS consult_factors (
    tenant_id      VARCHAR(128)  NOT NULL,
    session_id     VARCHAR(191)  NOT NULL,
    factors_json   JSON          NOT NULL,
    updated_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                   ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_id, session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kb_jobs (
    id             VARCHAR(64)   NOT NULL,
    tenant_id      VARCHAR(128)  NOT NULL,
    doc_dir        VARCHAR(1024) NOT NULL,
    status         VARCHAR(32)   NOT NULL DEFAULT 'queued',
    progress       INT           NOT NULL DEFAULT 0,
    message        VARCHAR(512)  NOT NULL DEFAULT '',
    chunk_count    INT           NOT NULL DEFAULT 0,
    error          TEXT          NULL,
    created_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                   ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_kb_tenant (tenant_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
