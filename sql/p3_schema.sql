-- P3：意图追踪与任务完整性维护（Intent Guard）

CREATE TABLE IF NOT EXISTS intent_anchors (
    tenant_id            VARCHAR(128)  NOT NULL,
    session_id           VARCHAR(191)  NOT NULL,
    goal                 VARCHAR(2000) NOT NULL,
    goal_raw             TEXT          NULL,
    anchor_history_json  JSON          NULL COMMENT '历史锚点（用户转向时归档）',
    turn_created         INT           NOT NULL DEFAULT 1,
    last_confirmed_turn  INT           NOT NULL DEFAULT 0,
    status               VARCHAR(32)   NOT NULL DEFAULT 'active' COMMENT 'active|replaced|closed',
    version              INT           NOT NULL DEFAULT 1,
    created_at           DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                         ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_id, session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话意图锚点';

CREATE TABLE IF NOT EXISTS intent_tasks (
    id             VARCHAR(64)   NOT NULL,
    tenant_id      VARCHAR(128)  NOT NULL,
    session_id     VARCHAR(191)  NOT NULL,
    anchor_version INT           NOT NULL DEFAULT 1,
    title          VARCHAR(512)  NOT NULL,
    status         VARCHAR(32)   NOT NULL DEFAULT 'pending'
                   COMMENT 'pending|in_progress|done|blocked|skipped',
    closed_by      VARCHAR(32)   NULL COMMENT 'check|planner|user',
    sort_order     INT           NOT NULL DEFAULT 0,
    closed_at      DATETIME(6)   NULL,
    created_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                  ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_itask_session (tenant_id, session_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话任务清单条目';

CREATE TABLE IF NOT EXISTS intent_checks (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id   VARCHAR(128)  NOT NULL,
    session_id  VARCHAR(191)  NOT NULL,
    turn_no     INT           NOT NULL DEFAULT 0,
    step_no     INT           NOT NULL DEFAULT 0 COMMENT 'agent 内第几步；0=回合级',
    phase       VARCHAR(32)   NOT NULL COMMENT 'pre_step|post_answer',
    verdict     VARCHAR(32)   NOT NULL COMMENT 'aligned|drift|irrelevant|error|timeout|complete|partial|not_started',
    reason      VARCHAR(1000) NULL,
    correction  VARCHAR(1000) NULL,
    action_json JSON          NULL,
    latency_ms  INT           NOT NULL DEFAULT 0,
    model       VARCHAR(128)  NULL,
    created_at  DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_icheck_session (session_id, created_at),
    KEY idx_icheck_tenant (tenant_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='意图对齐检查审计';
