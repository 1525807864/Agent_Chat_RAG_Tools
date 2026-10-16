-- 租户成员：一人一租户一条；角色决定能调用哪些写接口
CREATE TABLE IF NOT EXISTS tenant_members (
  tenant_id   VARCHAR(128) NOT NULL,
  user_id     VARCHAR(128) NOT NULL,
  role        VARCHAR(32)  NOT NULL,
  status      VARCHAR(16)  NOT NULL DEFAULT 'active',
  invited_by  VARCHAR(128) NULL,
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, user_id),
  KEY idx_tenant_members_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- 统一后台任务：API 只入队，Worker 消费
CREATE TABLE IF NOT EXISTS jobs (
  id           VARCHAR(64)  NOT NULL,
  job_type     VARCHAR(64)  NOT NULL,
  tenant_id    VARCHAR(128) NOT NULL,
  user_id      VARCHAR(128) NOT NULL,
  status       VARCHAR(16)  NOT NULL DEFAULT 'queued',
  progress     INT          NOT NULL DEFAULT 0,
  message      VARCHAR(512) NOT NULL DEFAULT '',
  payload_json JSON         NULL,
  result_json  JSON         NULL,
  error        TEXT         NULL,
  attempts     INT          NOT NULL DEFAULT 0,
  created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at   TIMESTAMP    NULL,
  finished_at  TIMESTAMP    NULL,
  updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_jobs_tenant_status (tenant_id, status),
  KEY idx_jobs_type_status (job_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
-- 可选：关键写操作审计（登录失败、改角色、开终端等）
CREATE TABLE IF NOT EXISTS audit_events (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id   VARCHAR(128) NOT NULL,
  actor_id    VARCHAR(128) NOT NULL,
  action      VARCHAR(64)  NOT NULL,
  resource    VARCHAR(128) NULL,
  ip          VARCHAR(64)  NULL,
  result      VARCHAR(16)  NOT NULL,
  detail      VARCHAR(512) NULL,
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_audit_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;