-- =====================================================================
-- V1__create_tables.sql
-- 14 张业务/支撑表。依据 backend/doc/数据架构设计-V1-五模块-MVP.md（DATA）。
-- 循环外键（gimbals.current_assessment_id 组合FK、members.created_from_assessment_id FK）
-- 与全部性能索引后置到 V2__deferred_fks_and_indexes.sql（见 decisions.md 第 5 条）。
-- 所有 FK 一律 ON DELETE RESTRICT（禁止级联物理删除）。
-- uuid 主键提供 gen_random_uuid() 默认值（PG16 内置），便于服务端与测试插入。
-- =====================================================================

-- 所有 JSONB 有 schema_version（DATA §4）——列级 CHECK 逐列执行（决策表见
-- backend/contracts/decisions-notes.md「JSONB schema_version 列决策」）。
-- 类型加固（oracle round-2 R2-4）：仅 `jsonb_exists` 存在性不够——数组可含
-- 字符串 "schema_version"，对象可含 null/字符串版本。非占位分支一律要求
-- `jsonb_typeof(col)='object' AND col ? 'schema_version' AND
--  jsonb_typeof(col->'schema_version')='number'`
-- （? 键存在判断不可省：缺键时 jsonb_typeof(NULL)=NULL，CHECK 会放过）：
--   F 形态 `col = '{}'::jsonb OR (object 且 schema_version 为 number)`：
--     NOT NULL DEFAULT '{}' 的阶段性摘要/观测列（空 = 尚未写入）；
--   N 形态 `col IS NULL OR (object 且 schema_version 为 number)`：可空业务内容列；
--   S 形态 `(object 且 schema_version 为 number)`：一旦建行必须有内容的事实载荷
--     （async_jobs.payload、care_records.payload、notifications.payload）。
--   例外（自由格式，不受版本号约束，注释于各表）：诊断类
--   last_error / failure_detail / failure_detail* ——错误快照非演进业务载荷。
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
    CONSTRAINT ck_idem_attempt_revision CHECK (attempt_revision >= 0),
    -- DATA §4（所有 JSONB 带 schema_version）：T13 摘要在 processing 阶段合法为
    -- 空占位 '{}'；服务端写入非空摘要时必须携带 schema_version（IdempotencyService
    -- completeSuccess/completeRejected 统一注入）。
    CONSTRAINT ck_idem_result_summary_schema CHECK (
        result_summary = '{}'::jsonb OR (jsonb_typeof(result_summary) = 'object' AND result_summary ? 'schema_version' AND jsonb_typeof(result_summary -> 'schema_version') = 'number')),
    CONSTRAINT ck_idem_verification_summary_schema CHECK (
        verification_summary = '{}'::jsonb OR (jsonb_typeof(verification_summary) = 'object' AND verification_summary ? 'schema_version' AND jsonb_typeof(verification_summary -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_accounts_auth_revision CHECK (auth_revision > 0),
    -- F 形态（DATA §4 JSONB schema_version）：profile 初始为空占位，写入须带版本
    CONSTRAINT ck_accounts_profile_schema CHECK (
        profile = '{}'::jsonb OR (jsonb_typeof(profile) = 'object' AND profile ? 'schema_version' AND jsonb_typeof(profile -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_members_status CHECK (status IN ('active','disabled')),
    -- F 形态：档案/身份摘要阶段性为空占位，写入须带 schema_version
    CONSTRAINT ck_members_profile_schema CHECK (
        profile = '{}'::jsonb OR (jsonb_typeof(profile) = 'object' AND profile ? 'schema_version' AND jsonb_typeof(profile -> 'schema_version') = 'number')),
    CONSTRAINT ck_members_identity_summary_schema CHECK (
        identity_summary = '{}'::jsonb OR (jsonb_typeof(identity_summary) = 'object' AND identity_summary ? 'schema_version' AND jsonb_typeof(identity_summary -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_grant_status CHECK (status IN ('active','revoked')),
    -- F 形态：授权快照/核验摘要（B 包 M1 写入时带 schema_version）
    CONSTRAINT ck_grant_member_summary_schema CHECK (
        member_summary = '{}'::jsonb OR (jsonb_typeof(member_summary) = 'object' AND member_summary ? 'schema_version' AND jsonb_typeof(member_summary -> 'schema_version') = 'number')),
    CONSTRAINT ck_grant_verification_summary_schema CHECK (
        verification_summary = '{}'::jsonb OR (jsonb_typeof(verification_summary) = 'object' AND verification_summary ? 'schema_version' AND jsonb_typeof(verification_summary -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_gimbal_status_revision CHECK (status_revision >= 0),
    -- F 形态：观测/事件快照（未上报时空占位合法；写入须带 schema_version）
    CONSTRAINT ck_gimbal_latest_observation_schema CHECK (
        latest_observation = '{}'::jsonb OR (jsonb_typeof(latest_observation) = 'object' AND latest_observation ? 'schema_version' AND jsonb_typeof(latest_observation -> 'schema_version') = 'number')),
    CONSTRAINT ck_gimbal_active_incidents_schema CHECK (
        active_incidents = '{}'::jsonb OR (jsonb_typeof(active_incidents) = 'object' AND active_incidents ? 'schema_version' AND jsonb_typeof(active_incidents -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_microcrystal_observation_seq CHECK (observation_seq >= 0),
    -- F 形态：DATA 表注（DD ~L725）"capabilities JSONB 内 schema_version"；未登记前空占位合法
    CONSTRAINT ck_microcrystal_capabilities_schema CHECK (
        capabilities = '{}'::jsonb OR (jsonb_typeof(capabilities) = 'object' AND capabilities ? 'schema_version' AND jsonb_typeof(capabilities -> 'schema_version') = 'number')),
    CONSTRAINT ck_microcrystal_latest_observation_schema CHECK (
        latest_observation = '{}'::jsonb OR (jsonb_typeof(latest_observation) = 'object' AND latest_observation ? 'schema_version' AND jsonb_typeof(latest_observation -> 'schema_version') = 'number'))
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
    ),
    -- F/N 形态（DATA §4）：photo_versions/identity_result 空占位合法；
    -- report_summary/report_payload 可空、有值必须带 schema_version。
    -- failure_code/failure_detail：错误快照，自由格式（例外，见文件头注释）
    CONSTRAINT ck_assessment_photo_versions_schema CHECK (
        photo_versions = '{}'::jsonb OR (jsonb_typeof(photo_versions) = 'object' AND photo_versions ? 'schema_version' AND jsonb_typeof(photo_versions -> 'schema_version') = 'number')),
    CONSTRAINT ck_assessment_identity_result_schema CHECK (
        identity_result = '{}'::jsonb OR (jsonb_typeof(identity_result) = 'object' AND identity_result ? 'schema_version' AND jsonb_typeof(identity_result -> 'schema_version') = 'number')),
    CONSTRAINT ck_assessment_report_summary_schema CHECK (
        report_summary IS NULL OR (jsonb_typeof(report_summary) = 'object' AND report_summary ? 'schema_version' AND jsonb_typeof(report_summary -> 'schema_version') = 'number')),
    CONSTRAINT ck_assessment_report_payload_schema CHECK (
        report_payload IS NULL OR (jsonb_typeof(report_payload) = 'object' AND report_payload ? 'schema_version' AND jsonb_typeof(report_payload -> 'schema_version') = 'number'))
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
    ),
    -- F/N 形态：输入快照/方案摘要空占位合法；plan_payload 有值必须带版本。
    -- failure_detail：错误快照，自由格式（例外）
    CONSTRAINT ck_plan_input_snapshot_schema CHECK (
        input_snapshot = '{}'::jsonb OR (jsonb_typeof(input_snapshot) = 'object' AND input_snapshot ? 'schema_version' AND jsonb_typeof(input_snapshot -> 'schema_version') = 'number')),
    CONSTRAINT ck_plan_plan_summary_schema CHECK (
        plan_summary = '{}'::jsonb OR (jsonb_typeof(plan_summary) = 'object' AND plan_summary ? 'schema_version' AND jsonb_typeof(plan_summary -> 'schema_version') = 'number')),
    CONSTRAINT ck_plan_plan_payload_schema CHECK (
        plan_payload IS NULL OR (jsonb_typeof(plan_payload) = 'object' AND plan_payload ? 'schema_version' AND jsonb_typeof(plan_payload -> 'schema_version') = 'number'))
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
    -- 按类型控制端归属（DATA T07：controller_account_id/installation "APP 执行时必填"，
    -- controller_gimbal_id "云台执行时必填；两类控制字段互斥"）。
    -- 互斥语义覆盖整个 APP 控制字段族 {account, installation}：gimbal 执行不留安装标识。
    CONSTRAINT ck_execution_controller_ownership CHECK (
        (controller_type = 'app'
            AND controller_account_id IS NOT NULL
            AND controller_installation_id IS NOT NULL
            AND controller_gimbal_id IS NULL)
        OR (controller_type = 'gimbal'
            AND controller_gimbal_id IS NOT NULL
            AND controller_account_id IS NULL
            AND controller_installation_id IS NULL)
    ),
    -- closed ⇔ closed_at 非空
    CONSTRAINT ck_execution_closed_iff_closed_at CHECK ((status = 'closed') = (closed_at IS NOT NULL)),
    CONSTRAINT ck_execution_verification_revision CHECK (verification_revision >= 0),
    CONSTRAINT ck_execution_accepted_count CHECK (accepted_count >= 0),
    CONSTRAINT ck_execution_last_observation_seq CHECK (last_observation_seq IS NULL OR last_observation_seq >= 0),
    -- F/N 形态：执行期冻结快照/核验/观测/收尾清单（DATA §4）。
    -- latest_observation 可空（未上报）；closure_manifest 可空（未收尾）
    CONSTRAINT ck_execution_plan_snapshot_schema CHECK (
        plan_snapshot = '{}'::jsonb OR (jsonb_typeof(plan_snapshot) = 'object' AND plan_snapshot ? 'schema_version' AND jsonb_typeof(plan_snapshot -> 'schema_version') = 'number')),
    CONSTRAINT ck_execution_latest_verification_schema CHECK (
        latest_verification = '{}'::jsonb OR (jsonb_typeof(latest_verification) = 'object' AND latest_verification ? 'schema_version' AND jsonb_typeof(latest_verification -> 'schema_version') = 'number')),
    CONSTRAINT ck_execution_latest_observation_schema CHECK (
        latest_observation IS NULL OR (jsonb_typeof(latest_observation) = 'object' AND latest_observation ? 'schema_version' AND jsonb_typeof(latest_observation -> 'schema_version') = 'number')),
    CONSTRAINT ck_execution_closure_manifest_schema CHECK (
        closure_manifest IS NULL OR (jsonb_typeof(closure_manifest) = 'object' AND closure_manifest ? 'schema_version' AND jsonb_typeof(closure_manifest -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_record_source_seq CHECK (source_seq > 0),
    -- S 形态：流水表内容不可变，业务载荷建行即须带 schema_version（无空占位阶段）
    CONSTRAINT ck_record_payload_schema CHECK (jsonb_typeof(payload) = 'object' AND payload ? 'schema_version' AND jsonb_typeof(payload -> 'schema_version') = 'number')
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
    -- active 须有账号归属、会话引用与非空通道注册（DD 9.x 表：T09 "active 必须有
    -- account/session/registration"——registration 为空对象即无注册，拒绝）
    CONSTRAINT ck_destination_active_fields CHECK (
        status <> 'active' OR (account_id IS NOT NULL AND session_ref IS NOT NULL
            AND registration <> '{}'::jsonb)
    ),
    -- F 形态：registration 未登记/已失效可空占位；写入通道信息须带 schema_version
    -- （active 行由上条 CHECK 强制非空，两条形合成 DD"active 必须有注册"）
    CONSTRAINT ck_destination_registration_schema CHECK (
        registration = '{}'::jsonb OR (jsonb_typeof(registration) = 'object' AND registration ? 'schema_version' AND jsonb_typeof(registration -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_notification_destination_revision CHECK (destination_revision >= 0),
    -- S 形态：通知建行即携带最小 payload（DD T10"payload 仅最小通知"，无空阶段）；
    -- last_error：错误快照，自由格式（例外）
    CONSTRAINT ck_notification_payload_schema CHECK (jsonb_typeof(payload) = 'object' AND payload ? 'schema_version' AND jsonb_typeof(payload -> 'schema_version') = 'number')
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
    CONSTRAINT ck_media_byte_size CHECK (byte_size IS NULL OR byte_size >= 0),
    -- F 形态：pending 无存储元数据为空占位；MediaService.markAvailable 写入带
    -- schema_version:1。last_error：错误快照，自由格式（例外）
    CONSTRAINT ck_media_storage_metadata_schema CHECK (
        storage_metadata = '{}'::jsonb OR (jsonb_typeof(storage_metadata) = 'object' AND storage_metadata ? 'schema_version' AND jsonb_typeof(storage_metadata -> 'schema_version') = 'number'))
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
    CONSTRAINT ck_job_payload_schema CHECK (jsonb_typeof(payload) = 'object' AND payload ? 'schema_version' AND jsonb_typeof(payload -> 'schema_version') = 'number')
);
-- 同一 owner 的 identity.enroll 在未完成态最多一个（防并发建档）
CREATE UNIQUE INDEX uq_job_identity_enroll
    ON async_jobs (owner_id)
    WHERE job_type = 'identity.enroll' AND status IN ('queued','running','failed');
