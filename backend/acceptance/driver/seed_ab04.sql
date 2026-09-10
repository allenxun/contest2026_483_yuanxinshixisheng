-- AB-04 约束负例的最小父链种子（E 专用库；合法 app 控制端形状）
INSERT INTO idempotency_requests (id, principal_type, principal_id, operation, idempotency_key, payload_hash) VALUES
 ('11111111-1111-4111-8111-111111111101','app_account','accept-seed','seed.op','k-asm-1','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111102','app_account','accept-seed','seed.op','k-exec-1','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111103','app_account','accept-seed','seed.op','k-exec-2','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111104','app_account','accept-seed','seed.op','k-exec-3','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111105','app_account','accept-seed','seed.op','k-asm-2','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111106','app_account','accept-seed','seed.op','k-asm-3','0000000000000000000000000000000000000000000000000000000000000000');
INSERT INTO accounts (id, login_provider, login_subject) VALUES ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','phone','+8613900000001');
INSERT INTO members (id, identity_namespace, face_subject_ref) VALUES ('22222222-2222-4222-8222-222222222201','accept-ns','face-seed-1');
INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version) VALUES ('33333333-3333-4333-8333-333333333301','GIM-ACCEPT-SEED','subject-seed-1',1);
INSERT INTO skin_assessments (id, gimbal_id, member_id, source_request_id) VALUES ('44444444-4444-4444-8444-444444444401','33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201','11111111-1111-4111-8111-111111111101');
INSERT INTO care_plans (id, assessment_id, member_id) VALUES ('55555555-5555-4555-8555-555555555501','44444444-4444-4444-8444-444444444401','22222222-2222-4222-8222-222222222201');
INSERT INTO microcrystals (id, serial_no) VALUES ('66666666-6666-4666-8666-666666666601','MC-ACCEPT-SEED');
INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, controller_account_id, controller_installation_id, assessment_id_at_start, source_request_id)
 VALUES ('77777777-7777-4777-8777-777777777701','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','inst-seed-owner','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111102');
INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id, microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload)
 VALUES ('99999999-9999-4999-8999-999999999901','77777777-7777-4777-8777-777777777701','rec-a','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601',1,'epoch-1',1,'a0000000000000000000000000000000000000000000000000000000000000001','{"schema_version":1}');
