-- =====================================================================
-- V2__deferred_fks_and_indexes.sql
-- 1) 两条循环外键后置补齐（先插任务再更新指针、字段可空；普通 FK，不 DEFERRABLE）；
-- 2) 数据架构设计-V1-五模块-MVP.md / spec-digest §2 列出的全部性能索引。
-- =====================================================================

-- ---------- 循环外键 ----------
-- T03 gimbals.current_assessment_id → T05 skin_assessments(gimbal_id, id) 组合外键：
-- 保证云台当前任务指针只能指向本云台的任务（跨云台指错任务被数据库拒绝）。
ALTER TABLE gimbals
    ADD CONSTRAINT fk_gimbal_current_assessment
    FOREIGN KEY (id, current_assessment_id)
    REFERENCES skin_assessments (gimbal_id, id)
    ON DELETE RESTRICT;

-- T01 members.created_from_assessment_id → T05 skin_assessments.id：
-- 首次可靠建档来源任务（与 T05.member_id → members 构成循环，故与组合外键同批后置）。
ALTER TABLE members
    ADD CONSTRAINT fk_member_created_from_assessment
    FOREIGN KEY (created_from_assessment_id)
    REFERENCES skin_assessments (id)
    ON DELETE RESTRICT;

-- ---------- 索引（按 DATA 文档编号注释） ----------

-- T03 gimbals：按绑定账号查询；离线扫描 (connection_status, last_seen_at)
CREATE INDEX idx_gimbal_bound_account ON gimbals (bound_account_id);
CREATE INDEX idx_gimbal_connection_seen ON gimbals (connection_status, last_seen_at);

-- T02 member_access_grants：M1-A02 授权列表分页（活跃部分唯一索引 uq_grant_active 见 V1）
CREATE INDEX idx_grants_account_status_created ON member_access_grants (account_id, status, created_at DESC, id);

-- T05 skin_assessments：M3-A04 成员历史报告列表（仅已发布报告）
CREATE INDEX idx_assessment_member_reports ON skin_assessments (member_id, report_ready_at DESC, id)
    WHERE report_id IS NOT NULL;

-- T06 care_plans：M4-A01 成员方案列表
CREATE INDEX idx_plan_member_created ON care_plans (member_id, created_at DESC, id);

-- T07 care_executions：M4-A09 成员护理历史；方案维度执行列表
CREATE INDEX idx_execution_member_created ON care_executions (member_id, created_at DESC, id);
CREATE INDEX idx_execution_plan_created ON care_executions (plan_id, created_at DESC, id);

-- T08 care_records：校验与重建 K（按方案接收顺序）
CREATE INDEX idx_record_plan_received ON care_records (plan_id, received_at, id);

-- T09 notification_destinations：按账号选择有效目标
CREATE INDEX idx_destination_account_status ON notification_destinations (account_id, status);

-- T11 media_objects：按任务照片版本、执行、请求定位与清理器扫描
CREATE INDEX idx_media_assessment_version ON media_objects (assessment_id, photo_version);
CREATE INDEX idx_media_execution ON media_objects (execution_id);
CREATE INDEX idx_media_request ON media_objects (request_id);
CREATE INDEX idx_media_state_created ON media_objects (state, created_at);

-- T12 async_jobs：领取扫描 (status, available_at, id)；租约到期回收扫描
CREATE INDEX idx_job_status_available ON async_jobs (status, available_at, id);
CREATE INDEX idx_job_status_lease ON async_jobs (status, lease_until);
