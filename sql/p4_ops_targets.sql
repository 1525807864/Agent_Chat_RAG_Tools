-- 客户可运维项目（Ops Target）
-- 一行 = 一个客户环境 / 一套集群；凭证密文字段，禁止 SELECT 后原样回前端

CREATE TABLE IF NOT EXISTS ops_targets (
    id              VARCHAR(64)   NOT NULL COMMENT '对外 ID，如 tgt_xxx',
    tenant_id       VARCHAR(128)  NOT NULL COMMENT '所属租户，必须与 JWT.tenant_id 一致',
    name            VARCHAR(256)  NOT NULL COMMENT '展示名，如 Acme 生产',
    -- platform=本平台集群；remote_agent=客户侧 Agent；dedicated_holmes=客户专用 Holmes
    target_type     VARCHAR(32)   NOT NULL DEFAULT 'remote_agent',
    enabled         TINYINT(1)    NOT NULL DEFAULT 1,
    default_namespace VARCHAR(128) NULL COMMENT '默认排查 ns，可空',
    -- remote_agent / dedicated_holmes 的 HTTP 根（无尾斜杠）
    endpoint_base   VARCHAR(1024) NULL,
    -- Fernet 密文：Agent Bearer / Holmes API Key；空表示不鉴权
    auth_token_enc  TEXT          NULL,
    -- Fernet 密文：完整 kubeconfig YAML（可选；给专用 Holmes/Agent 侧使用，平台不落盘常驻）
    kubeconfig_enc  TEXT          NULL,
    -- 备注，给管理员看
    notes           VARCHAR(1000) NULL,
    created_by      VARCHAR(128)  NOT NULL DEFAULT '',
    created_at      DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                  ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_ops_tgt_tenant (tenant_id, enabled),
    KEY idx_ops_tgt_tenant_name (tenant_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运维目标项目（多客户）';