# shellcheck shell=bash
# B 验收检查定义（组 1：12 API 有效/无效主体）b1..b13。
# 由 backend/tests/run-acceptance-b.sh source；依赖其提供的辅助函数与变量。

b01() {
  local phone inst face member meta key
  phone=$(new_phone); inst="inst-b1-$(new_id | cut -c1-8)"
  login_app "$phone" "$inst"
  face="$TMP/b1.face"; make_face "$face" "b1-$RANDOM"
  member=$(seed_member "$face")
  meta="$TMP/b1.meta"; write_meta "$meta" cap-b1 consent-b1
  key="key-b1-$(new_id)"
  post_grant "$APP_TOKEN" "$key" "$face" "$meta"
  aeq "$CODE" 201 "M1-A01 201"
  hakeys data "grantId,memberId,status,grantedAt"
  aeq "$(jget data.status)" active "status"
  aeq "$(jget data.memberId)" "$member" "memberId"
  grep -q verification_summary <<<"$BODY" && fail "verification_summary 泄漏"
  local gid t13 src
  gid=$(jget data.grantId)
  src=$(psql_b "SELECT source_request_id FROM member_access_grants WHERE id='$gid'")
  t13=$(psql_b "SELECT id FROM idempotency_requests WHERE operation='m1-a01-create-member-access-grant' AND idempotency_key='$key'")
  aeq "$src" "$t13" "T02.source_request_id=T13.id"
  printf '%s' "$APP_TOKEN" > "$TMP/b1.token"; printf '%s' "$key" > "$TMP/b1.key"
  printf '%s' "$gid" > "$TMP/b1.grant"; printf '%s' "$member" > "$TMP/b1.member"
  vlog "grant=$gid member=$member 字段集合精确；T13 链接一致"
}

b02() {
  local face meta
  face="$TMP/b2.face"; make_face "$face" "b2-$RANDOM"
  meta="$TMP/b2.meta"; write_meta "$meta" cap-b2 consent-b2
  local aref="A-B2-$RANDOM"; seed_gimbal "G-B2-$RANDOM" "$aref" 1 >/dev/null
  gimbal_login "$aref" 1
  post_grant "$G_TOKEN" "k-b2a-$RANDOM" "$face" "$meta"
  aeq "$CODE" 403 "云台 token"; aeq "$(jget error.code)" CALLER_NOT_ALLOWED "code"
  op_call m1A01CreateMemberAccessGrant POST "$WEB/api/v1/member-access-grants" \
    -H "Idempotency-Key: k-b2b-$RANDOM" -F "metadata=@$meta;type=application/json" -F "face=@$face;type=image/png"
  aeq "$CODE" 401 "无 token"; aeq "$(jget error.code)" AUTH_REQUIRED "code"
  local meta2="$TMP/b2.meta2"; write_meta "$meta2" cap-b2b consent-b2 ",\"memberId\":\"$(new_id)\""
  post_grant "$(cat "$TMP/b1.token")" "k-b2c-$RANDOM" "$face" "$meta2"
  aeq "$CODE" 400 "memberId 字段"; aeq "$(jget error.code)" INVALID_INPUT "code"
  local c2 m2
  c2=$(psql_b "SELECT count(*) FROM member_access_grants"); m2=$(psql_b "SELECT count(*) FROM members")
  make_face "$face" "b2-nomatch-$RANDOM"
  login_app "$(new_phone)" "inst-b2-$(new_id|cut -c1-8)"
  post_grant "$APP_TOKEN" "k-b2d-$RANDOM" "$face" "$meta"
  aeq "$CODE" 403 "无可靠匹配"; aeq "$(jget error.code)" FACE_NOT_VERIFIED "code"
  aeq "$(psql_b "SELECT count(*) FROM member_access_grants")" "$c2" "T02 零新行"
  aeq "$(psql_b "SELECT count(*) FROM members")" "$m2" "members 零新行"
  vlog "403/401/400/403(FACE_NOT_VERIFIED) 如期且零副作用"
}

b03() {
  local token; token=$(cat "$TMP/b1.token")
  local acct; acct=$(psql_b "SELECT account_id FROM member_access_grants WHERE id='$(cat "$TMP/b1.grant")'")
  local rmember; rmember=$(psql_b "INSERT INTO members (id) VALUES (gen_random_uuid()) RETURNING id")
  local tid; tid=$(new_id)
  psql_bf <<SQL
INSERT INTO idempotency_requests (id,principal_type,principal_id,operation,idempotency_key,payload_hash,status)
VALUES ('$tid','app_account','seed-b3','seed.b3','seed-b3-$RANDOM','0000000000000000000000000000000000000000000000000000000000000000','succeeded');
INSERT INTO member_access_grants (id,account_id,member_id,status,revoked_at,source_request_id)
VALUES (gen_random_uuid(),'$acct','$rmember','revoked',now(),'$tid');
SQL
  local rg; rg=$(psql_b "SELECT id FROM member_access_grants WHERE account_id='$acct' AND status='revoked' LIMIT 1")
  list_grants "$token"
  aeq "$CODE" 200 "A02 200"; hakeys data "items,nextCursor"
  grep -q "$rg" <<<"$BODY" && fail "revoked grant 出现在 active 列表"
  grep -q "$(cat "$TMP/b1.grant")" <<<"$BODY" || fail "active grant 未出现在列表"
  local aref="A-B3-$RANDOM"; seed_gimbal "G-B3-$RANDOM" "$aref" 1 >/dev/null; gimbal_login "$aref" 1
  list_grants "$G_TOKEN"; aeq "$CODE" 403 "云台 list"; aeq "$(jget error.code)" CALLER_NOT_ALLOWED "code"
  op_call m1A02ListMemberAccessGrants GET "$WEB/api/v1/me/member-access-grants" \
    -H "Authorization: Bearer $token" --get --data-urlencode 'cursor=!!!not-base64!!!'
  aeq "$CODE" 400 "非法 cursor"; aeq "$(jget error.code)" INVALID_INPUT "code"
  vlog "仅 active；云台 403；非法 cursor 400"
}

b04() {
  login_app "$(new_phone)" "inst-b4-$(new_id|cut -c1-8)"
  local token="$APP_TOKEN"
  local face member meta key
  face="$TMP/b4.face"; make_face "$face" "b4-$RANDOM"; member=$(seed_member "$face")
  meta="$TMP/b4.meta"; write_meta "$meta" cap-b4 consent-b4; key="k-b4-$(new_id)"
  post_grant "$token" "$key" "$face" "$meta"; aeq "$CODE" 201 "create"
  local grant; grant=$(jget data.grantId)
  op_call m1A03RevokeMemberAccessGrant DELETE "$WEB/api/v1/me/member-access-grants/$grant" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: kd-b4-$RANDOM"
  aeq "$CODE" 204 "撤销 204"; aeq "$BODY" "" "204 无 body"
  local t1; t1=$(psql_b "SELECT revoked_at::text FROM member_access_grants WHERE id='$grant'")
  op_call m1A03RevokeMemberAccessGrant DELETE "$WEB/api/v1/me/member-access-grants/$grant" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: kd2-b4-$RANDOM"
  aeq "$CODE" 204 "重复撤销"
  aeq "$(psql_b "SELECT revoked_at::text FROM member_access_grants WHERE id='$grant'")" "$t1" "revoked_at 不变"
  op_call m1A03RevokeMemberAccessGrant DELETE "$WEB/api/v1/me/member-access-grants/$(cat "$TMP/b1.grant")" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: kf-b4-$RANDOM"
  aeq "$CODE" 404 "他人 grant"; printf '%s' "$BODY" > "$TMP/b4.other"
  op_call m1A03RevokeMemberAccessGrant DELETE "$WEB/api/v1/me/member-access-grants/$(new_id)" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: km-b4-$RANDOM"
  aeq "$CODE" 404 "不存在"; printf '%s' "$BODY" > "$TMP/b4.missing"
  mask "$TMP/b4.other" > "$TMP/b4.o"; mask "$TMP/b4.missing" > "$TMP/b4.m"
  cmp -s "$TMP/b4.o" "$TMP/b4.m" || fail "他人/不存在 404 掩蔽 requestId 后不一致"
  vlog "204（重复 revoked_at 不变）；他人/不存在 404 不可区分"
}

b05() {
  local aref="A-B5-$RANDOM"; local gid; gid=$(seed_gimbal "G-B5-$RANDOM" "$aref" 1)
  local before; before=$(t03snap "$gid")
  gimbal_login "$aref" 1
  aeq "$G_ID" "$gid" "gimbalId"
  hakeys data "gimbalId,sessionToken,expiresAt,serverTime"
  grep -qi member <<<"$BODY" && fail "会话响应含 member"
  op_call m2A01CreateGimbalSession POST "$WEB/api/v1/gimbal-sessions" -H 'Content-Type: application/json' \
    -d '{"credential":"wrong-cred","credentialVersion":"1","proof":"p"}'
  aeq "$CODE" 401 "错凭据"; aeq "$(jget error.code)" AUTH_REQUIRED "code"
  op_call m2A01CreateGimbalSession POST "$WEB/api/v1/gimbal-sessions" -H 'Content-Type: application/json' \
    -d "{\"credential\":\"$aref\",\"credentialVersion\":\"9\",\"proof\":\"p\"}"
  aeq "$CODE" 401 "错代次"; aeq "$(jget error.code)" AUTH_REQUIRED "code"
  aeq "$(t03snap "$gid")" "$before" "T03 未变"
  vlog "合法 200；错凭据/代次 401；T03 last_seen/status 未变"
}

b06() {
  local aref="A-B6-$RANDOM"; local gid; gid=$(seed_gimbal "G-B6-$RANDOM" "$aref" 1)
  gimbal_login "$aref" 1
  local ls0; ls0=$(psql_b "SELECT coalesce(last_seen_at::text,'NULL') FROM gimbals WHERE id='$gid'")
  aeq "$ls0" NULL "初始 last_seen NULL"
  hb_op "$G_TOKEN" "$gid" "e1" "1"
  aeq "$CODE" 200 "心跳 200"; aeq "$(jget data.accepted)" true "accepted"
  [[ "$(psql_b "SELECT coalesce(last_seen_at::text,'NULL') FROM gimbals WHERE id='$gid'")" != NULL ]] || fail "last_seen 未推进"
  hb_op "$(cat "$TMP/b1.token")" "$gid" "e1" "2"
  aeq "$CODE" 403 "APP 心跳"; aeq "$(jget error.code)" CALLER_NOT_ALLOWED "code"
  local aref2="A-B6b-$RANDOM"; seed_gimbal "G-B6b-$RANDOM" "$aref2" 1 >/dev/null
  gimbal_login "$aref2" 1
  hb_op "$G_TOKEN" "$gid" "e1" "3"
  aeq "$CODE" 404 "他云台"; printf '%s' "$BODY" > "$TMP/b6.other"
  op_call m2A02ReportGimbalHeartbeat POST "$WEB/api/v1/gimbals/$(new_id)/heartbeats" \
    -H "Authorization: Bearer $G_TOKEN" -H 'Content-Type: application/json' \
    -d '{"observationEpoch":"e1","observationSeq":"1","observedAt":"2026-09-11T10:00:00Z","powerState":"awake"}'
  aeq "$CODE" 404 "不存在"; printf '%s' "$BODY" > "$TMP/b6.missing"
  mask "$TMP/b6.other" > "$TMP/b6.o"; mask "$TMP/b6.missing" > "$TMP/b6.m"
  cmp -s "$TMP/b6.o" "$TMP/b6.m" || fail "他云台/不存在 404 不一致"
  vlog "self accepted 推进；APP 403；他云台/不存在 404 一致"
}

b07() {
  local aref="A-B7-$RANDOM"; local gid; gid=$(seed_gimbal "G-B7-$RANDOM" "$aref" 1)
  login_app "$(new_phone)" "inst-b7-$(new_id|cut -c1-8)"
  psql_b "UPDATE gimbals SET bound_account_id='$APP_ID',binding_revision=1,bound_at=now() WHERE id='$gid'" >/dev/null
  local before; before=$(t03snap "$gid")
  op_call m2A03GetGimbalStatus GET "$WEB/api/v1/gimbals/$gid/status" -H "Authorization: Bearer $APP_TOKEN"
  aeq "$CODE" 200 "绑定账号 200"; aeq "$(jget data.isStale)" true "isStale（last_seen 空）"
  gimbal_login "$aref" 1
  op_call m2A03GetGimbalStatus GET "$WEB/api/v1/gimbals/$gid/status" -H "Authorization: Bearer $G_TOKEN"
  aeq "$CODE" 200 "云台自身 200"
  login_app "$(new_phone)" "inst-b7o-$(new_id|cut -c1-8)"
  op_call m2A03GetGimbalStatus GET "$WEB/api/v1/gimbals/$gid/status" -H "Authorization: Bearer $APP_TOKEN"
  aeq "$CODE" 404 "其他账号"; printf '%s' "$BODY" > "$TMP/b7.other"
  op_call m2A03GetGimbalStatus GET "$WEB/api/v1/gimbals/$(new_id)/status" -H "Authorization: Bearer $APP_TOKEN"
  aeq "$CODE" 404 "不存在"; printf '%s' "$BODY" > "$TMP/b7.missing"
  mask "$TMP/b7.other" > "$TMP/b7.o"; mask "$TMP/b7.missing" > "$TMP/b7.m"
  cmp -s "$TMP/b7.o" "$TMP/b7.m" || fail "其他/不存在 404 不一致"
  aeq "$(t03snap "$gid")" "$before" "GET 无副作用"
  vlog "绑定账号/云台自身 200；其他/不存在 404 一致；isStale=true；GET 无副作用"
}

b08() {
  login_app "$(new_phone)" "inst-b8-$(new_id|cut -c1-8)"
  local acct="$APP_ID" inst="$INST" serial="MC-B8-$RANDOM"
  local proof; proof=$(connection_proof_app "$acct" "$inst" "$serial")
  op_call m2A04ReportMicrocrystalObservation POST "$WEB/api/v1/microcrystal-observations" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k8a-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"microcrystalSerial\":\"$serial\",\"connectionProof\":\"$proof\",\"capabilities\":{\"schemaVersion\":1,\"revision\":\"1\",\"foo\":\"bar\"},\"observationEpoch\":\"e1\",\"observationSeq\":\"5\",\"observedAt\":\"2026-09-11T10:00:00Z\",\"state\":{\"k\":1}}"
  aeq "$CODE" 200 "observe 200"; aeq "$(jget data.accepted)" true "accepted"
  local mid; mid=$(jget data.microcrystalId)
  aeq "$(psql_b "SELECT jsonb_typeof(capabilities->'schema_version') FROM microcrystals WHERE id='$mid'")" number "schema_version 为 number"
  aeq "$(psql_b "SELECT observer_type FROM microcrystals WHERE id='$mid'")" app_account "observer_type"
  aeq "$(psql_b "SELECT observer_ref FROM microcrystals WHERE id='$mid'")" "$acct:$inst" "observer_ref 来自 token"
  aeq "$(psql_b "SELECT capabilities->>'revision' FROM microcrystals WHERE id='$mid'")" 1 "revision=1"
  local s2="MC-B8b-$RANDOM"
  op_call m2A04ReportMicrocrystalObservation POST "$WEB/api/v1/microcrystal-observations" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k8b-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"microcrystalSerial\":\"$s2\",\"connectionProof\":\"not-a-proof\",\"capabilities\":{\"schemaVersion\":1,\"revision\":\"1\"},\"observationEpoch\":\"e1\",\"observationSeq\":\"1\",\"observedAt\":\"2026-09-11T10:00:00Z\",\"state\":{}}"
  aeq "$CODE" 400 "坏证明"; aeq "$(jget error.code)" INVALID_INPUT "code"
  local proof3; proof3=$(connection_proof_app "$acct" "$inst" "$serial")
  op_call m2A04ReportMicrocrystalObservation POST "$WEB/api/v1/microcrystal-observations" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k8c-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"microcrystalSerial\":\"$serial\",\"connectionProof\":\"$proof3\",\"capabilities\":{\"schemaVersion\":1,\"revision\":\"2\",\"foo\":\"stale\"},\"observationEpoch\":\"e1\",\"observationSeq\":\"3\",\"observedAt\":\"2026-09-11T10:00:00Z\",\"state\":{}}"
  aeq "$CODE" 200 "旧 seq 200"; aeq "$(jget data.accepted)" false "旧 seq rejected"
  aeq "$(psql_b "SELECT capabilities->>'revision' FROM microcrystals WHERE id='$mid'")" 1 "能力未被覆盖"
  printf '%s' "$mid" > "$TMP/b8.mid"; printf '%s' "$serial" > "$TMP/b8.serial"
  printf '%s' "$APP_TOKEN" > "$TMP/b8.token"; printf '%s' "$acct" > "$TMP/b8.acct"; printf '%s' "$inst" > "$TMP/b8.inst"
  vlog "accepted；schema_version 整数；observer 来自 token；旧 seq 不覆盖能力"
}

b09() {
  local mid serial token acct inst
  mid=$(cat "$TMP/b8.mid"); serial=$(cat "$TMP/b8.serial"); token=$(cat "$TMP/b8.token")
  acct=$(cat "$TMP/b8.acct"); inst=$(cat "$TMP/b8.inst")
  local proof; proof=$(connection_proof_app "$acct" "$inst" "$serial")
  op_call m2A05GetMicrocrystalCapabilities GET "$WEB/api/v1/microcrystals/$mid/capabilities" \
    -H "Authorization: Bearer $token" -H "X-Connection-Proof: $proof"
  aeq "$CODE" 200 "capabilities 200"; hakeys data "capabilities,capabilityRevision,observedAt,receivedAt,isStale"
  local s3="MC-B9-$(new_id)"
  local id3; id3=$(psql_b "INSERT INTO microcrystals (id,serial_no) VALUES (gen_random_uuid(),'$s3') RETURNING id")
  op_call m2A05GetMicrocrystalCapabilities GET "$WEB/api/v1/microcrystals/$id3/capabilities" -H "Authorization: Bearer $token"
  aeq "$CODE" 403 "从未观察"; aeq "$(jget error.code)" CALLER_NOT_ALLOWED "code"
  local oid; oid=$(psql_b "INSERT INTO microcrystals (id,serial_no,observer_type,observer_ref,observation_epoch,observation_seq) VALUES (gen_random_uuid(),'MC-B9o-$RANDOM','app_account','$(new_id):inst-x','e1',9) RETURNING id")
  op_call m2A05GetMicrocrystalCapabilities GET "$WEB/api/v1/microcrystals/$oid/capabilities" -H "Authorization: Bearer $token"
  aeq "$CODE" 404 "他人微晶"; printf '%s' "$BODY" > "$TMP/b9.other"
  op_call m2A05GetMicrocrystalCapabilities GET "$WEB/api/v1/microcrystals/$(new_id)/capabilities" -H "Authorization: Bearer $token"
  aeq "$CODE" 404 "不存在"; printf '%s' "$BODY" > "$TMP/b9.missing"
  mask "$TMP/b9.other" > "$TMP/b9.o"; mask "$TMP/b9.missing" > "$TMP/b9.m"
  cmp -s "$TMP/b9.o" "$TMP/b9.m" || fail "他人/不存在 404 不一致"
  vlog "有权 200 字段集合精确；未观察 403；他人/不存在 404 一致"
}

b10() {
  login_app "$(new_phone)" "inst-b10-$(new_id|cut -c1-8)"
  local acct="$APP_ID" inst="$INST"
  local g1; g1=$(seed_gimbal "G-B10a-$RANDOM" "A-B10a-$RANDOM" 1)
  local p1; p1=$(pairing_proof "$g1" "$acct" "$inst")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g1" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k10a-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"0\",\"pairingProof\":\"$p1\"}"
  aeq "$CODE" 200 "bind 200"; aeq "$(jget data.bindingStatus)" self "self"
  aeq "$(jget data.bindingRevision)" 1 "revision 1"
  aeq "$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g1'")" 1 "DB rev1"
  local g2; g2=$(seed_gimbal "G-B10b-$RANDOM" "A-B10b-$RANDOM" 1)
  local other; other=$(psql_b "INSERT INTO accounts (id,login_provider,login_subject) VALUES (gen_random_uuid(),'phone','o10-$RANDOM') RETURNING id")
  psql_b "UPDATE gimbals SET bound_account_id='$other',binding_revision=1,bound_at=now() WHERE id='$g2'" >/dev/null
  local p2; p2=$(pairing_proof "$g2" "$acct" "$inst")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g2" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k10b-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"1\",\"pairingProof\":\"$p2\"}"
  aeq "$CODE" 409 "已绑他人"; aeq "$(jget error.code)" BOUND_TO_OTHER "code"
  aeq "$(psql_b "SELECT bound_account_id FROM gimbals WHERE id='$g2'")" "$other" "原绑定保持"
  local g3; g3=$(seed_gimbal "G-B10c-$RANDOM" "A-B10c-$RANDOM" 1)
  local p3; p3=$(pairing_proof "$g3" "$acct" "$inst")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g3" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k10c-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"5\",\"pairingProof\":\"$p3\"}"
  aeq "$CODE" 409 "代次不符"; aeq "$(jget error.code)" BINDING_CHANGED "code"
  local g4; g4=$(seed_gimbal "G-B10d-$RANDOM" "A-B10d-$RANDOM" 1)
  local pbad; pbad=$(tamper_proof "$(pairing_proof "$g4" "$acct" "$inst")")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g4" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k10d-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"0\",\"pairingProof\":\"$pbad\"}"
  aeq "$CODE" 403 "无效证明"; aeq "$(jget error.code)" CALLER_NOT_ALLOWED "code"
  local g5; g5=$(seed_gimbal "G-B10e-$RANDOM" "A-B10e-$RANDOM" 1)
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g5" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k10e-$RANDOM" -H 'Content-Type: application/json' \
    -d '{"expectedBindingRevision":"0"}'
  aeq "$CODE" 400 "缺证明字段"; aeq "$(jget error.code)" INVALID_INPUT "code"
  vlog "self/+1；BOUND_TO_OTHER/BINDING_CHANGED 409；坏证明 403；缺字段 400"
}

b11() {
  login_app "$(new_phone)" "inst-b11-$(new_id|cut -c1-8)"
  local acct="$APP_ID" inst="$INST"
  local gu; gu=$(seed_gimbal "G-B11u-$RANDOM" "A-B11u-$RANDOM" 1)
  local p; p=$(pairing_proof "$gu" "$acct" "$inst")
  op_call m2A07GetGimbalBindingStatus GET "$WEB/api/v1/gimbals/$gu/binding-status" \
    -H "Authorization: Bearer $APP_TOKEN" -H "X-Pairing-Proof: $p"
  aeq "$CODE" 200 "unbound"; aeq "$(jget data.bindingStatus)" unbound "status"
  local gs; gs=$(seed_gimbal "G-B11s-$RANDOM" "A-B11s-$RANDOM" 1)
  psql_b "UPDATE gimbals SET bound_account_id='$acct',binding_revision=1,bound_at=now() WHERE id='$gs'" >/dev/null
  local ps; ps=$(pairing_proof "$gs" "$acct" "$inst")
  op_call m2A07GetGimbalBindingStatus GET "$WEB/api/v1/gimbals/$gs/binding-status" \
    -H "Authorization: Bearer $APP_TOKEN" -H "X-Pairing-Proof: $ps"
  aeq "$CODE" 200 "self"; aeq "$(jget data.bindingStatus)" self "status"
  local go; go=$(seed_gimbal "G-B11o-$RANDOM" "A-B11o-$RANDOM" 1)
  local other; other=$(psql_b "INSERT INTO accounts (id,login_provider,login_subject) VALUES (gen_random_uuid(),'phone','o11-$RANDOM') RETURNING id")
  psql_b "UPDATE gimbals SET bound_account_id='$other',binding_revision=1,bound_at=now() WHERE id='$go'" >/dev/null
  local po; po=$(pairing_proof "$go" "$acct" "$inst")
  op_call m2A07GetGimbalBindingStatus GET "$WEB/api/v1/gimbals/$go/binding-status" \
    -H "Authorization: Bearer $APP_TOKEN" -H "X-Pairing-Proof: $po"
  aeq "$CODE" 200 "other"; aeq "$(jget data.bindingStatus)" other "status"
  hakeys data "bindingStatus,bindingRevision"
  local before; before=$(t03snap "$gu")
  op_call m2A07GetGimbalBindingStatus GET "$WEB/api/v1/gimbals/$gu/binding-status" -H "Authorization: Bearer $APP_TOKEN"
  aeq "$CODE" 400 "缺头"; aeq "$(jget error.code)" INVALID_INPUT "code"
  aeq "$(t03snap "$gu")" "$before" "GET 无副作用"
  vlog "unbound/self/other；other 仅两字段；缺头 400；GET 无副作用"
}

b12() {
  login_app "$(new_phone)" "inst-b12-$(new_id|cut -c1-8)"
  local acct="$APP_ID" inst="$INST"
  local g; g=$(seed_gimbal "G-B12-$RANDOM" "A-B12-$RANDOM" 1)
  local p; p=$(pairing_proof "$g" "$acct" "$inst")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k12-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"0\",\"pairingProof\":\"$p\"}"
  aeq "$CODE" 200 "bind"
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: ku12-$RANDOM" -H 'If-Match: "binding-1"'
  aeq "$CODE" 204 "解绑 204"
  aeq "$(psql_b "SELECT coalesce(bound_account_id::text,'NULL') FROM gimbals WHERE id='$g'")" NULL "bound null"
  aeq "$(psql_b "SELECT coalesce(bound_at::text,'NULL') FROM gimbals WHERE id='$g'")" NULL "bound_at null"
  local rev; rev=$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g'")
  aeq "$rev" 2 "revision +1"
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: ku12b-$RANDOM"
  aeq "$CODE" 204 "重复解绑"
  aeq "$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g'")" "$rev" "重复不再递增"
  local g2; g2=$(seed_gimbal "G-B12b-$RANDOM" "A-B12b-$RANDOM" 1)
  local other; other=$(psql_b "INSERT INTO accounts (id,login_provider,login_subject) VALUES (gen_random_uuid(),'phone','o12-$RANDOM') RETURNING id")
  psql_b "UPDATE gimbals SET bound_account_id='$other',binding_revision=1,bound_at=now() WHERE id='$g2'" >/dev/null
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g2" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: ku12c-$RANDOM"
  aeq "$CODE" 404 "他人无 If-Match"
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g2" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: ku12d-$RANDOM" -H 'If-Match: "binding-1"'
  aeq "$CODE" 409 "他人相符 If-Match"; aeq "$(jget error.code)" BINDING_CHANGED "code"
  aeq "$(psql_b "SELECT bound_account_id FROM gimbals WHERE id='$g2'")" "$other" "他人绑定完好"
  vlog "自解绑 null/+1；重复不递增；他人 404/409 且绑定完好"
}

b13() {
  login_app "$(new_phone)" "inst-b13-$(new_id|cut -c1-8)"
  local token="$APP_TOKEN" inst="$INST"
  op_call m5A01RegisterNotificationDestination PUT "$WEB/api/v1/me/notification-destinations/$inst" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: k13-$RANDOM" -H 'Content-Type: application/json' \
    -d '{"provider":"dev-fcm","platform":"android","registration":{"token":"dev-token"},"expectedDestinationRevision":"0"}'
  aeq "$CODE" 200 "登记 200"; hakeys data "destinationId,destinationRevision,status"
  aeq "$(jget data.destinationRevision)" 1 "revision 1"
  local did; did=$(jget data.destinationId)
  aeq "$(psql_b "SELECT jsonb_typeof(registration->'schema_version') FROM notification_destinations WHERE id='$did'")" number "registration 整数版本"
  op_call m5A01RegisterNotificationDestination PUT "$WEB/api/v1/me/notification-destinations/other-inst" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: k13b-$RANDOM" -H 'Content-Type: application/json' \
    -d '{"provider":"dev-fcm","platform":"android","registration":{"token":"t"},"expectedDestinationRevision":"0"}'
  aeq "$CODE" 403 "路径不符"; aeq "$(jget error.code)" CALLER_NOT_ALLOWED "code"
  local n1; n1=$(psql_b "SELECT count(*) FROM notification_destinations")
  op_call m5A01RegisterNotificationDestination PUT "$WEB/api/v1/me/notification-destinations/none" \
    -H "Idempotency-Key: k13c-$RANDOM" -H 'Content-Type: application/json' \
    -d '{"provider":"dev-fcm","platform":"android","registration":{"token":"t"},"expectedDestinationRevision":"0"}'
  aeq "$CODE" 401 "无 token"; aeq "$(jget error.code)" AUTH_REQUIRED "code"
  aeq "$(psql_b "SELECT count(*) FROM notification_destinations")" "$n1" "T09 零新行"
  vlog "首登三字段；registration 整数版本；路径不符 403；无 token 401 零行"
}
