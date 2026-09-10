-- =====================================================================
-- V1__create_tables.sql
-- 14 张业务/支撑表。依据 backend/doc/数据架构设计-V1-五模块-MVP.md（DATA）。
-- 循环外键（gimbals.current_assessment_id 组合FK、members.created_from_assessment_id FK）
-- 与全部性能索引后置到 V2__deferred_fks_and_indexes.sql（见 decisions.md 第 5 条）。
-- 所有 FK 一律 ON DELETE RESTRICT（禁止级联物理删除）。
-- uuid 主键提供 gen_random_uuid() 默认值（PG16 内置），便于服务端与测试插入。
-- =====================================================================

-- T13 idempotency_requests：一个主体一次逻辑写请求（无外部 FK，先建供 source_request_id 引用）
CREATE TABLE idempotency_requests (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_type       text NOT NULL,          -- {app_account, gimbal}
    principal_id         text NOT NULL,          -- 规范化文本主体引用（多态，无 FK）
    operation            text NOT NULL,
    idempotency_key      text NOT NULL,
    payload_hash         text NOT NULL,
    status               text NOT NULL DEFAULT 'processing',
    lease_until          timestamptz,
    attempt_revision     bigint NOT NULL DEFAULT 0,
    resource_type        text,
    resource_id          uuid,
    result_summary       jsonb NOT NULL DEFAULT '{}'::jsonb,
    verification_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_idem_principal UNIQUE (principal_type, principal_id, operation, idempotency_key),
    CONSTRAINT ck_idem_status CHECK (status IN ('processing','succeeded','rejected')),
    CONSTRAINT ck_idem_attempt_revision CHECK (attempt_revision >= 0)
);

-- T14 accounts：APP 登录账号宽表
CREATE TABLE accounts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    login_provider text NOT NULL,
    login_subject  text NOT NULL,
    status         text NOT NULL DEFAULT 'active',
    auth_revision  bigint NOT NULL DEFAULT 1,
    profile        jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_login_at  timestamptz,
    disabled_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_accounts_login UNIQUE (login_provider, login_subject),
    CONSTRAINT ck_accounts_status CHECK (status IN ('active','disabled')),
    CONSTRAINT ck_accounts_auth_revision CHECK (auth_revision > 0)
);

-- T01 members：一个人的档案（created_from_assessment_id 的组合外键后置 V2）
CREATE TABLE members (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_namespace          text,
    face_subject_ref            text,
    profile                     jsonb NOT NULL DEFAULT '{}'::jsonb,
    identity_summary            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_from_assessment_id  uuid,
    status                      text NOT NULL DEFAULT 'active',
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_members_status CHECK (status IN ('active','disabled'))
);
-- 可靠建档后 (identity_namespace, face_subject_ref) 组合唯一；建档前两列可空 → 部分唯一索引
CREATE UNIQUE INDEX uq_members_identity
    ON members (identity_namespace, face_subject_ref)
    WHERE identity_namespace IS NOT NULL AND face_subject_ref IS NOT NULL;

-- T02 member_access_grants：账号—成员一次授权关系
CREATE TABLE member_access_grants (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id            uuid NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    member_id             uuid NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
    status                text NOT NULL DEFAULT 'active',
    granted_at            timestamptz NOT NULL DEFAULT now(),
    revoked_at            timestamptz,
    member_summary        jsonb NOT NULL DEFAULT '{}'::jsonb,
    verification_summary  jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_request_id     uuid NOT NULL REFERENCES idempotency_requests(id) ON DELETE RESTRICT,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_grant_source UNIQUE (source_request_id),
    CONSTRAINT ck_grant_status CHECK (status IN ('active','revoked'))
);
-- 同一 (account_id, member_id) 最多一条 active 授权（部分唯一索引）
CREATE UNIQUE INDEX uq_grant_active
    ON member_access_grants (account_id, member_id)
    WHERE status = 'active';

-- T03 gimbals：云台宽表（current_assessment_id 组合外键后置 V2）
CREATE TABLE gimbals (
    id                            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_no                     text NOT NULL,
    auth_subject_ref              text NOT NULL,
    credential_version            bigint NOT NULL DEFAULT 1,
    bound_account_id              uuid REFERENCES accounts(id) ON DELETE RESTRICT,
    binding_revision              bigint NOT NULL DEFAULT 0,
    bound_at                      timestamptz,
    current_assessment_id         uuid,
    current_assessment_revision   bigint NOT NULL DEFAULT 0,
    last_seen_at                  timestamptz,
    connection_status             text NOT NULL DEFAULT 'unknown',
    status_revision               bigint NOT NULL DEFAULT 0,
    latest_observation            jsonb NOT NULL DEFAULT '{}'::jsonb,
    active_incidents              jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at                    timestamptz NOT NULL DEFAULT now(),
    updated_at                    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_gimbal_serial UNIQUE (serial_no),
    CONSTRAINT ck_gimbal_credential_version CHECK (credential_version >= 1),
    CONSTRAINT ck_gimbal_binding_revision CHECK (binding_revision >= 0),
    CONSTRAINT ck_gimbal_current_assessment_revision CHECK (current_assessment_revision >= 0),
    CONSTRAINT ck_gimbal_status_revision CHECK (status_revision >= 0)
);

-- T04 microcrystals：微晶宽表（无 current_controller，占用从 care_executions 查询）
CREATE TABLE microcrystals (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_no           text NOT NULL,
    capabilities        jsonb NOT NULL DEFAULT '{}'::jsonb,
    latest_observation  jsonb NOT NULL DEFAULT '{}'::jsonb,
    observer_type       text,
    observer_ref        text,
    observation_epoch   text,
    observation_seq     bigint,
    observed_at         timestamptz,
    received_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_microcrystal_serial UNIQUE (serial_no),
    CONSTRAINT ck_microcrystal_observation_seq CHECK (observation_seq >= 0)
);

-- T05 skin_assessments：测肤任务/统一报告宽表
CREATE TABLE skin_assessments (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gimbal_id               uuid NOT NULL REFERENCES gimbals(id) ON DELETE RESTRICT,
    member_id               uuid REFERENCES members(id) ON DELETE RESTRICT,
    status                  text NOT NULL DEFAULT 'queued',
    current_photo_version   bigint NOT NULL DEFAULT 1,
    processing_revision     bigint NOT NULL DEFAULT 0,
    photo_versions          jsonb NOT NULL DEFAULT '{}'::jsonb,
    identity_result         jsonb NOT NULL DEFAULT '{}'::jsonb,
    report_id               uuid,
    report_summary          jsonb,
    report_payload          jsonb,
    report_photo_version    bigint,
    report_ready_at         timestamptz,
    failure_code            text,
    failure_detail          jsonb,
    source_request_id       uuid NOT NULL REFERENCES idempotency_requests(id) ON DELETE RESTRICT,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_assessment_gimbal_id UNIQUE (gimbal_id, id),   -- 供 V2 组合外键引用
    CONSTRAINT uq_assessment_report UNIQUE (report_id),
    CONSTRAINT uq_assessment_source UNIQUE (source_request_id),
    CONSTRAINT ck_assessment_status CHECK (status IN ('queued','analyzing','needs_retake','report_ready','failed')),
    CONSTRAINT ck_assessment_current_photo_version CHECK (current_photo_version > 0),
    CONSTRAINT ck_assessment_processing_revision CHECK (processing_revision >= 0),
    CONSTRAINT ck_assessment_report_photo_version CHECK (report_photo_version IS NULL OR report_photo_version > 0),
    -- report_ready 必须有成员、报告 ID、结果载荷与依据照片版本（单行跨列 CHECK）
    CONSTRAINT ck_assessment_report_ready_requires_fields CHECK (
        status <> 'report_ready'
        OR (member_id IS NOT NULL AND report_id IS NOT NULL
            AND report_payload IS NOT NULL AND report_photo_version IS NOT NULL)
    )
);

-- T06 care_plans：护理方案与进度宽表
CREATE TABLE care_plans (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id        uuid NOT NULL REFERENCES skin_assessments(id) ON DELETE RESTRICT,
    member_id            uuid NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
    generation_status    text NOT NULL DEFAULT 'waiting_inputs',
    input_photo_version  bigint,
    generation_revision  bigint NOT NULL DEFAULT 0,
    input_snapshot       jsonb NOT NULL DEFAULT '{}'::jsonb,
    plan_summary         jsonb NOT NULL DEFAULT '{}'::jsonb,
    plan_payload         jsonb,
    target_count         bigint,
    completed_count      bigint NOT NULL DEFAULT 0,
    completed_at         timestamptz,
    progress_revision    bigint NOT NULL DEFAULT 0,
    failure_detail       jsonb,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_plan_assessment UNIQUE (assessment_id),
    CONSTRAINT ck_plan_generation_status CHECK (generation_status IN ('waiting_inputs','generating','ready','failed')),
    CONSTRAINT ck_plan_input_photo_version CHECK (input_photo_version IS NULL OR input_photo_version > 0),
    CONSTRAINT ck_plan_generation_revision CHECK (generation_revision >= 0),
    CONSTRAINT ck_plan_completed_count CHECK (completed_count >= 0),
    CONSTRAINT ck_plan_progress_revision CHECK (progress_revision >= 0),
    CONSTRAINT ck_plan_target_count CHECK (target_count IS NULL OR target_count > 0),
    -- ready 时 N>0 且正式方案载荷非空（单行跨列 CHECK）
    CONSTRAINT ck_plan_ready_requires_payload CHECK (
        generation_status <> 'ready'
        OR (target_count IS NOT NULL AND target_count > 0 AND plan_payload IS NOT NULL)
    )
);

-- T07 care_executions：一次护理执行宽表
CREATE TABLE care_executions (
    id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id                    uuid NOT NULL REFERENCES care_plans(id) ON DELETE RESTRICT,
    member_id                  uuid NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
    microcrystal_id            uuid NOT NULL REFERENCES microcrystals(id) ON DELETE RESTRICT,
    controller_type            text NOT NULL,
    controller_account_id      uuid REFERENCES accounts(id) ON DELETE RESTRICT,
    controller_installation_id text,
    controller_gimbal_id       uuid REFERENCES gimbals(id) ON DELETE RESTRICT,
    assessment_id_at_start     uuid NOT NULL REFERENCES skin_assessments(id) ON DELETE RESTRICT,
    plan_snapshot              jsonb NOT NULL DEFAULT '{}'::jsonb,
    status                     text NOT NULL DEFAULT 'admitted',
    verification_revision      bigint NOT NULL DEFAULT 0,
    last_verified_at           timestamptz,
    latest_verification        jsonb NOT NULL DEFAULT '{}'::jsonb,
    observation_epoch          text,
    last_observation_seq       bigint,
    latest_observation         jsonb,
    accepted_count             bigint NOT NULL DEFAULT 0,
    closure_manifest           jsonb,
    stopped_at                 timestamptz,
    closed_at                  timestamptz,
    source_request_id          uuid NOT NULL REFERENCES idempotency_requests(id) ON DELETE RESTRICT,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_execution_source UNIQUE (source_request_id),
    CONSTRAINT ck_execution_status CHECK (status IN ('admitted','running','paused','unknown','stopped','closed')),
    CONSTRAINT ck_execution_controller_type CHECK (controller_type IN ('app','gimbal')),
    -- 两类控制端互斥
    CONSTRAINT ck_execution_controller_exclusive CHECK (
        NOT (controller_account_id IS NOT NULL AND controller_gimbal_id IS NOT NULL)
    ),
    -- closed ⇔ closed_at 非空
    CONSTRAINT ck_execution_closed_iff_closed_at CHECK ((status = 'closed') = (closed_at IS NOT NULL)),
    CONSTRAINT ck_execution_verification_revision CHECK (verification_revision >= 0),
    CONSTRAINT ck_execution_accepted_count CHECK (accepted_count >= 0),
    CONSTRAINT ck_execution_last_observation_seq CHECK (last_observation_seq IS NULL OR last_observation_seq >= 0)
);
-- 同一微晶最多一个未收尾执行（仅 closed_at 非空释放占用）
CREATE UNIQUE INDEX uq_execution_open_microcrystal
    ON care_executions (microcrystal_id)
    WHERE closed_at IS NULL;
-- 一台云台最多一个未收尾控制执行
CREATE UNIQUE INDEX uq_execution_open_gimbal
    ON care_executions (controller_gimbal_id)
    WHERE controller_gimbal_id IS NOT NULL AND closed_at IS NULL;

-- T08 care_records：实际完成记录明细账（内容不可变，仅 created_at）
CREATE TABLE care_records (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id     uuid NOT NULL REFERENCES care_executions(id) ON DELETE RESTRICT,
    client_record_id text NOT NULL,
    plan_id          uuid NOT NULL REFERENCES care_plans(id) ON DELETE RESTRICT,
    member_id        uuid NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
    microcrystal_id  uuid NOT NULL REFERENCES microcrystals(id) ON DELETE RESTRICT,
    count_delta      bigint NOT NULL,
    source_epoch     text NOT NULL,
    source_seq       bigint NOT NULL,
    occurred_at      timestamptz,
    received_at      timestamptz NOT NULL DEFAULT now(),
    payload_hash     text NOT NULL,
    payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_record_client UNIQUE (execution_id, client_record_id),
    CONSTRAINT uq_record_source UNIQUE (execution_id, source_epoch, source_seq),
    CONSTRAINT ck_record_count_delta CHECK (count_delta > 0),
    CONSTRAINT ck_record_source_seq CHECK (source_seq > 0)
);

-- T09 notification_destinations：一个 APP 安装实例推送目标
CREATE TABLE notification_destinations (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    installation_id       text NOT NULL,
    account_id            uuid REFERENCES accounts(id) ON DELETE RESTRICT,
    destination_revision  bigint NOT NULL DEFAULT 0,
    provider              text,
    platform              text,
    registration          jsonb NOT NULL DEFAULT '{}'::jsonb,
    status                text NOT NULL DEFAULT 'active',
    session_ref           text,
    last_registered_at    timestamptz,
    invalidated_at        timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_destination_installation UNIQUE (installation_id),
    CONSTRAINT ck_destination_status CHECK (status IN ('active','disabled','invalid')),
    CONSTRAINT ck_destination_revision CHECK (destination_revision >= 0),
    -- active 须有账号归属与会话引用
    CONSTRAINT ck_destination_active_fields CHECK (
        status <> 'active' OR (account_id IS NOT NULL AND session_ref IS NOT NULL)
    )
);

-- T10 notifications：一次异常 × 一个目标
CREATE TABLE notifications (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gimbal_id              uuid NOT NULL REFERENCES gimbals(id) ON DELETE RESTRICT,
    incident_id            text NOT NULL,
    event_type             text NOT NULL,
    account_id             uuid NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    binding_revision       bigint NOT NULL,
    destination_id         uuid NOT NULL REFERENCES notification_destinations(id) ON DELETE RESTRICT,
    destination_revision   bigint NOT NULL,
    payload                jsonb NOT NULL DEFAULT '{}'::jsonb,
    status                 text NOT NULL DEFAULT 'pending',
    attempt_count          bigint NOT NULL DEFAULT 0,
    last_attempt_at        timestamptz,
    provider_message_id    text,
    last_error             jsonb,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_notification_dedup UNIQUE (gimbal_id, incident_id, binding_revision, destination_id, destination_revision),
    CONSTRAINT ck_notification_status CHECK (status IN ('pending','sending','submitted','delivered','failed','cancelled','unknown')),
    CONSTRAINT ck_notification_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_notification_binding_revision CHECK (binding_revision >= 0),
    CONSTRAINT ck_notification_destination_revision CHECK (destination_revision >= 0)
);

-- T11 media_objects：OSS 图片元数据
CREATE TABLE media_objects (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket            text NOT NULL,
    object_key        text NOT NULL,
    purpose           text NOT NULL,
    assessment_id     uuid REFERENCES skin_assessments(id) ON DELETE RESTRICT,
    photo_version     bigint,
    execution_id      uuid REFERENCES care_executions(id) ON DELETE RESTRICT,
    request_id        uuid REFERENCES idempotency_requests(id) ON DELETE RESTRICT,
    member_id         uuid REFERENCES members(id) ON DELETE RESTRICT,
    uploader_type     text,
    uploader_ref      text,
    state             text NOT NULL DEFAULT 'pending',
    content_type      text,
    byte_size         bigint,
    content_hash      text,
    storage_metadata  jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_error        jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_media_bucket_key UNIQUE (bucket, object_key),
    CONSTRAINT ck_media_purpose CHECK (purpose IN ('assessment_source','assessment_result','grant_face','execution_face','revalidation_face')),
    CONSTRAINT ck_media_state CHECK (state IN ('pending','available','failed','deleting','deleted')),
    CONSTRAINT ck_media_photo_version CHECK (photo_version IS NULL OR photo_version > 0),
    CONSTRAINT ck_media_byte_size CHECK (byte_size IS NULL OR byte_size >= 0)
);

-- T12 async_jobs：可靠异步工作队列
CREATE TABLE async_jobs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type         text NOT NULL,
    dedup_key        text NOT NULL,
    owner_type       text NOT NULL,
    owner_id         uuid NOT NULL,
    input_revision   bigint NOT NULL DEFAULT 0,
    payload          jsonb NOT NULL,
    status           text NOT NULL DEFAULT 'queued',
    available_at     timestamptz NOT NULL DEFAULT now(),
    attempt_count    bigint NOT NULL DEFAULT 0,
    max_attempts     bigint NOT NULL DEFAULT 5,
    lease_owner      text,
    lease_until      timestamptz,
    lease_revision   bigint NOT NULL DEFAULT 0,
    last_error       jsonb,
    finished_at      timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_dedup UNIQUE (dedup_key),
    CONSTRAINT ck_job_status CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
    CONSTRAINT ck_job_input_revision CHECK (input_revision >= 0),
    CONSTRAINT ck_job_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_job_max_attempts CHECK (max_attempts >= 1),
    CONSTRAINT ck_job_lease_revision CHECK (lease_revision >= 0),
    -- payload 必须携带 schema_version
    CONSTRAINT ck_job_payload_schema CHECK (jsonb_exists(payload, 'schema_version'))
);
-- 同一 owner 的 identity.enroll 在未完成态最多一个（防并发建档）
CREATE UNIQUE INDEX uq_job_identity_enroll
    ON async_jobs (owner_id)
    WHERE job_type = 'identity.enroll' AND status IN ('queued','running','failed');
