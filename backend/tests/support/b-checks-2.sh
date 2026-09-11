# shellcheck shell=bash
# B 验收检查定义（组 2/3/4）：b15..b26。由 run-acceptance-b.sh source。

b15() {
  local g; g=$(seed_gimbal "G-B15-$RANDOM" "A-B15-$RANDOM" 1)
  login_app "$(new_phone)" "inst-b15a-$(new_id|cut -c1-8)"; local ta="$APP_TOKEN" aa="$APP_ID" ia="$INST"
  login_app "$(new_phone)" "inst-b15b-$(new_id|cut -c1-8)"; local tb="$APP_TOKEN" ab="$APP_ID" ib="$INST"
  local pa pb; pa=$(pairing_proof "$g" "$aa" "$ia"); pb=$(pairing_proof "$g" "$ab" "$ib")
  ( call PUT "$WEB/api/v1/me/gimbal-bindings/$g" -H "Authorization: Bearer $ta" -H "Idempotency-Key: k15a-$RANDOM" -H 'Content-Type: application/json' -d "{\"expectedBindingRevision\":\"0\",\"pairingProof\":\"$pa\"}"; echo "$CODE" > "$TMP/b15.a" ) &
  ( call PUT "$WEB/api/v1/me/gimbal-bindings/$g" -H "Authorization: Bearer $tb" -H "Idempotency-Key: k15b-$RANDOM" -H 'Content-Type: application/json' -d "{\"expectedBindingRevision\":\"0\",\"pairingProof\":\"$pb\"}"; echo "$CODE" > "$TMP/b15.b" ) &
  wait
  local ca cb; ca=$(cat "$TMP/b15.a"); cb=$(cat "$TMP/b15.b")
  if [[ "$ca $cb" != "200 409" && "$ca $cb" != "409 200" ]]; then fail "并发应恰一 200 一 409，实际 $ca/$cb"; fi
  aeq "$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g'")" 1 "binding_revision=1"
  local bound; bound=$(psql_b "SELECT bound_account_id FROM gimbals WHERE id='$g'")
  if [[ "$bound" != "$aa" && "$bound" != "$ab" ]]; then fail "bound_account 非参与者: $bound"; fi
  aeq "$(psql_b "SELECT count(*) FROM gimbals WHERE id='$g' AND bound_account_id IS NOT NULL")" 1 "唯一绑定"
  vlog "真实并发：$ca/$cb；DB 唯一绑定 rev=1"
}

b16() {
  local g; g=$(seed_gimbal "G-B16-$RANDOM" "A-B16-$RANDOM" 1)
  login_app "$(new_phone)" "inst-b16a-$(new_id|cut -c1-8)"; local ta="$APP_TOKEN" aa="$APP_ID" ia="$INST"
  local pa; pa=$(pairing_proof "$g" "$aa" "$ia")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $ta" -H "Idempotency-Key: k16a-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"0\",\"pairingProof\":\"$pa\"}"
  aeq "$CODE" 200 "A 绑定"
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $ta" -H "Idempotency-Key: ku16a-$RANDOM" -H 'If-Match: "binding-1"'
  aeq "$CODE" 204 "A 解绑（If-Match binding-1）"
  login_app "$(new_phone)" "inst-b16b-$(new_id|cut -c1-8)"; local tb="$APP_TOKEN" ab="$APP_ID" ib="$INST"
  local rev_after_unbind; rev_after_unbind=$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g'")
  local pb; pb=$(pairing_proof "$g" "$ab" "$ib")
  op_call m2A06BindGimbal PUT "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $tb" -H "Idempotency-Key: k16b-$RANDOM" -H 'Content-Type: application/json' \
    -d "{\"expectedBindingRevision\":\"$rev_after_unbind\",\"pairingProof\":\"$pb\"}"
  aeq "$CODE" 200 "B 绑定"
  local rev_b; rev_b=$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g'")
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $ta" -H "Idempotency-Key: ku16b-$RANDOM" -H 'If-Match: "binding-1"'
  aeq "$CODE" 409 "A 旧 If-Match"; aeq "$(jget error.code)" BINDING_CHANGED "code"
  aeq "$(psql_b "SELECT bound_account_id FROM gimbals WHERE id='$g'")" "$ab" "仍是 B 绑定"
  aeq "$(psql_b "SELECT binding_revision FROM gimbals WHERE id='$g'")" "$rev_b" "代次未变"
  op_call m2A08UnbindGimbal DELETE "$WEB/api/v1/me/gimbal-bindings/$g" \
    -H "Authorization: Bearer $ta" -H "Idempotency-Key: ku16c-$RANDOM"
  aeq "$CODE" 404 "A 无 If-Match"
  aeq "$(psql_b "SELECT bound_account_id FROM gimbals WHERE id='$g'")" "$ab" "B 绑定仍完好"
  vlog "A rev1→unbind rev$rev_after_unbind→B rev$rev_b；A 旧解绑 409/404，B 未被解除"
}

b17() {
  login_app "$(new_phone)" "inst-b17-$(new_id|cut -c1-8)"
  local token="$APP_TOKEN"
  local face member meta
  face="$TMP/b17.face"; make_face "$face" "b17-$RANDOM"; member=$(seed_member "$face")
  meta="$TMP/b17.meta"; write_meta "$meta" cap-b17 consent-b17
  post_grant "$token" "k17-$RANDOM" "$face" "$meta"; aeq "$CODE" 201 "grant"
  local grant; grant=$(jget data.grantId)
  local g; g=$(seed_gimbal "G-B17-$RANDOM" "A-B17-$RANDOM" 1)
  local t13 aid mid rid okey bytes size hash
  t13=$(new_id); aid=$(new_id); mid=$(new_id); rid=$(new_id)
  okey="dev/assessment_result/$mid"; bytes="$TMP/b17.bin"
  printf 'REPORT-IMAGE-%s' "$RANDOM" > "$bytes"
  mkdir -p "$STORAGE_ROOT/dev/assessment_result"; cp "$bytes" "$STORAGE_ROOT/$okey"
  size=$(wc -c < "$bytes"); hash=$($HELP sha256 "$bytes")
  psql_bf <<SQL
INSERT INTO idempotency_requests (id,principal_type,principal_id,operation,idempotency_key,payload_hash,status)
VALUES ('$t13','app_account','seed-b17','seed.b17','seed-b17-$RANDOM','0000000000000000000000000000000000000000000000000000000000000000','succeeded');
INSERT INTO skin_assessments (id,gimbal_id,member_id,status,current_photo_version,report_id,report_payload,report_photo_version,report_ready_at,source_request_id)
VALUES ('$aid','$g','$member','report_ready',1,'$rid',CAST('{"schema_version":1,"images":[{"media_id":"$mid"}]}' AS jsonb),1,now(),'$t13');
INSERT INTO media_objects (id,bucket,object_key,purpose,assessment_id,photo_version,member_id,state,content_type,byte_size,content_hash,storage_metadata)
VALUES ('$mid','mvp-a-media','$okey','assessment_result','$aid',1,'$member','available','image/jpeg',$size,'$hash','{"schema_version":1}');
SQL
  local code
  code=$(curl -sS --noproxy '*' -D "$TMP/b17.hdr" -o "$TMP/b17.out" -w '%{http_code}' \
    "$WEB/api/v1/media/$mid/content" -H "Authorization: Bearer $token")
  aeq "$code" 200 "media 200"
  cmp -s "$bytes" "$TMP/b17.out" || fail "字节不一致"
  grep -qi 'cache-control: no-store' "$TMP/b17.hdr" || fail "缺 Cache-Control: no-store"
  grep -qi 'x-content-type-options: nosniff' "$TMP/b17.hdr" || fail "缺 nosniff"
  printf '%s' "$token" > "$TMP/b17.token"; printf '%s' "$grant" > "$TMP/b17.grant"
  printf '%s' "$mid" > "$TMP/b17.media"; printf '%s' "$member" > "$TMP/b17.member"
  vlog "report_ready+公开引用 → 200 正确字节 + no-store + nosniff"
}

b18() {
  local token grant mid
  token=$(cat "$TMP/b17.token"); grant=$(cat "$TMP/b17.grant"); mid=$(cat "$TMP/b17.media")
  op_call m1A03RevokeMemberAccessGrant DELETE "$WEB/api/v1/me/member-access-grants/$grant" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: k18-$RANDOM"
  aeq "$CODE" 204 "撤销"
  local code
  code=$(curl -sS --noproxy '*' -o "$TMP/b18.after" -w '%{http_code}' "$WEB/api/v1/media/$mid/content" -H "Authorization: Bearer $token")
  aeq "$code" 404 "撤销后 404"
  code=$(curl -sS --noproxy '*' -o "$TMP/b18.missing" -w '%{http_code}' "$WEB/api/v1/media/$(new_id)/content" -H "Authorization: Bearer $token")
  aeq "$code" 404 "不存在 404"
  mask "$TMP/b18.after" > "$TMP/b18.a"; mask "$TMP/b18.missing" > "$TMP/b18.m"
  cmp -s "$TMP/b18.a" "$TMP/b18.m" || fail "撤销后 404 与不存在 404 不一致"
  aeq "$(psql_b "SELECT state FROM media_objects WHERE id='$mid'")" available "媒体行未删除"
  vlog "撤销即时 404 且与不存在一致；媒体行保留"
}

b19() {
  local token key face meta grant member acct
  token=$(cat "$TMP/b1.token"); key=$(cat "$TMP/b1.key"); face="$TMP/b1.face"
  meta="$TMP/b1.meta"; grant=$(cat "$TMP/b1.grant"); member=$(cat "$TMP/b1.member")
  acct=$(psql_b "SELECT account_id FROM member_access_grants WHERE id='$grant'")
  op_call m1A03RevokeMemberAccessGrant DELETE "$WEB/api/v1/me/member-access-grants/$grant" \
    -H "Authorization: Bearer $token" -H "Idempotency-Key: k19-$RANDOM"
  aeq "$CODE" 204 "撤销 b1 grant"
  post_grant "$token" "$key" "$face" "$meta"
  aeq "$CODE" 403 "旧请求重放"; aeq "$(jget error.code)" GRANT_REVOKED "code"
  aeq "$(psql_b "SELECT count(*) FROM member_access_grants WHERE account_id='$acct' AND member_id='$member'")" 1 "无新行"
  aeq "$(psql_b "SELECT status FROM member_access_grants WHERE id='$grant'")" revoked "原行 revoked"
  post_grant "$token" "kn19-$RANDOM" "$face" "$meta"
  aeq "$CODE" 201 "新键"; local newg; newg=$(jget data.grantId)
  aneq "$newg" "$grant" "新 grantId"
  aeq "$(psql_b "SELECT count(*) FROM member_access_grants WHERE account_id='$acct' AND member_id='$member'")" 2 "两行（revoked+active）"
  aeq "$(psql_b "SELECT status FROM member_access_grants WHERE id='$grant'")" revoked "旧行仍 revoked"
  vlog "旧请求重放 403 GRANT_REVOKED；新键 201；旧 revoked 行保留"
}

b20() {
  login_app "$(new_phone)" "inst-b20-$(new_id|cut -c1-8)"
  local token="$APP_TOKEN"
  local face member; face="$TMP/b20.face"; make_face "$face" "b20-$RANDOM"; member=$(seed_member "$face")
  local meta="$TMP/b20.meta"; write_meta "$meta" cap-b20 consent-b20
  post_grant "$token" "k20-$RANDOM" "$face" "$meta"; aeq "$CODE" 201 "grant"
  local aref="A-B20g-$RANDOM"; local g; g=$(seed_gimbal "G-B20g-$RANDOM" "$aref" 1)
  gimbal_login "$aref" 1
  local purpose m code
  for purpose in grant_face execution_face revalidation_face; do
    m=$(psql_b "INSERT INTO media_objects (id,bucket,object_key,purpose,state,content_type,byte_size,storage_metadata) VALUES (gen_random_uuid(),'mvp-a-media','dev/$purpose/$(new_id)','$purpose','available','image/jpeg',3,'{\"schema_version\":1}') RETURNING id")
    code=$(curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "$WEB/api/v1/media/$m/content" -H "Authorization: Bearer $token")
    aeq "$code" 404 "face=$purpose 应 404"
  done
  local mf; mf=$(psql_b "SELECT id FROM media_objects WHERE purpose='grant_face' LIMIT 1")
  code=$(curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "$WEB/api/v1/media/$mf/content" -H "Authorization: Bearer $G_TOKEN")
  aeq "$code" 404 "云台 face 也应 404"
  # 公开引用判别力
  local t13 aid mid rid g2 okey bytes
  g2=$(seed_gimbal "G-B20b-$RANDOM" "A-B20b-$RANDOM" 1)
  t13=$(new_id); aid=$(new_id); mid=$(new_id); rid=$(new_id)
  okey="dev/assessment_result/$mid"; bytes="$TMP/b20.bin"; printf 'PUB-%s' "$RANDOM" > "$bytes"
  mkdir -p "$STORAGE_ROOT/dev/assessment_result"; cp "$bytes" "$STORAGE_ROOT/$okey"
  psql_bf <<SQL
INSERT INTO idempotency_requests (id,principal_type,principal_id,operation,idempotency_key,payload_hash,status)
VALUES ('$t13','app_account','seed-b20','seed.b20','seed-b20-$RANDOM','0000000000000000000000000000000000000000000000000000000000000000','succeeded');
INSERT INTO skin_assessments (id,gimbal_id,member_id,status,current_photo_version,report_id,report_payload,report_photo_version,report_ready_at,source_request_id)
VALUES ('$aid','$g2','$member','report_ready',1,'$rid',CAST('{"schema_version":1,"images":[]}' AS jsonb),1,now(),'$t13');
INSERT INTO media_objects (id,bucket,object_key,purpose,assessment_id,photo_version,member_id,state,content_type,byte_size,content_hash,storage_metadata)
VALUES ('$mid','mvp-a-media','$okey','assessment_result','$aid',1,'$member','available','image/jpeg',$(wc -c < "$bytes"),'$($HELP sha256 "$bytes")','{"schema_version":1}');
SQL
  code=$(curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "$WEB/api/v1/media/$mid/content" -H "Authorization: Bearer $token")
  aeq "$code" 404 "未被冻结报告 images[] 引用 应 404"
  # 判别力：仅把该 mediaId 加入 D 冻结格式 report_payload.images[]，其余条件不变 → 200
  psql_b "UPDATE skin_assessments SET report_payload=CAST('{\"schema_version\":1,\"images\":[{\"media_id\":\"$mid\"}]}' AS jsonb) WHERE id='$aid'" >/dev/null
  code=$(curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "$WEB/api/v1/media/$mid/content" -H "Authorization: Bearer $token")
  aeq "$code" 200 "被冻结报告 images[] 引用 应 200"
  vlog "face 三用途及云台全 404；images[] 未引用 404 → 引用后 200（判别力）"
}

b21() {
  local aref="A-B21-$RANDOM"; local g; g=$(seed_gimbal "G-B21-$RANDOM" "$aref" 1)
  local member; member=$(psql_b "INSERT INTO members (id) VALUES (gen_random_uuid()) RETURNING id")
  local t13 t13b a1 a2 mid rid okey bytes
  t13=$(new_id); t13b=$(new_id); a1=$(new_id); a2=$(new_id); mid=$(new_id); rid=$(new_id); okey="dev/assessment_result/$mid"
  bytes="$TMP/b21.bin"; printf 'CUR-%s' "$RANDOM" > "$bytes"
  mkdir -p "$STORAGE_ROOT/dev/assessment_result"; cp "$bytes" "$STORAGE_ROOT/$okey"
  psql_bf <<SQL
INSERT INTO idempotency_requests (id,principal_type,principal_id,operation,idempotency_key,payload_hash,status)
VALUES ('$t13','gimbal','seed-b21','seed.b21','seed-b21-$RANDOM','0000000000000000000000000000000000000000000000000000000000000000','succeeded');
INSERT INTO idempotency_requests (id,principal_type,principal_id,operation,idempotency_key,payload_hash,status)
VALUES ('$t13b','gimbal','seed-b21b','seed.b21b','seed-b21b-$RANDOM','0000000000000000000000000000000000000000000000000000000000000000','succeeded');
INSERT INTO skin_assessments (id,gimbal_id,member_id,status,current_photo_version,report_id,report_payload,report_photo_version,report_ready_at,source_request_id)
VALUES ('$a1','$g','$member','report_ready',1,'$rid',CAST('{"schema_version":1,"images":[{"media_id":"$mid"}]}' AS jsonb),1,now(),'$t13');
INSERT INTO skin_assessments (id,gimbal_id,member_id,status,current_photo_version,report_id,report_payload,report_photo_version,report_ready_at,source_request_id)
VALUES ('$a2','$g','$member','report_ready',1,'$(new_id)',CAST('{"schema_version":1,"images":[{"media_id":"$mid"}]}' AS jsonb),1,now(),'$t13b');
UPDATE gimbals SET current_assessment_id='$a1' WHERE id='$g';
INSERT INTO media_objects (id,bucket,object_key,purpose,assessment_id,photo_version,member_id,state,content_type,byte_size,content_hash,storage_metadata)
VALUES ('$mid','mvp-a-media','$okey','assessment_result','$a1',1,'$member','available','image/jpeg',$(wc -c < "$bytes"),'$($HELP sha256 "$bytes")','{"schema_version":1}');
SQL
  gimbal_login "$aref" 1
  local code
  code=$(curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "$WEB/api/v1/media/$mid/content" -H "Authorization: Bearer $G_TOKEN")
  aeq "$code" 200 "当前任务 200"
  psql_b "UPDATE gimbals SET current_assessment_id='$a2' WHERE id='$g'" >/dev/null
  code=$(curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' "$WEB/api/v1/media/$mid/content" -H "Authorization: Bearer $G_TOKEN")
  aeq "$code" 404 "旧任务 404"
  vlog "云台当前任务 200；指向他任务后 404（仅当前任务）"
}

b22() {
  local aref="A-B22-$RANDOM"; local g; g=$(seed_gimbal "G-B22-$RANDOM" "$aref" 1)
  gimbal_login "$aref" 1
  local i
  for i in 1 2 3; do
    hb_op "$G_TOKEN" "$g" "e1" "$i"; aeq "$CODE" 200 "hb $i"; aeq "$(jget data.accepted)" true "accepted $i"
  done
  local snap; snap=$(t03snap "$g")
  hb_op "$G_TOKEN" "$g" "e1" "2"; aeq "$(jget data.accepted)" false "重放 seq2"
  hb_op "$G_TOKEN" "$g" "e1" "1"; aeq "$(jget data.accepted)" false "迟到 seq1"
  aeq "$(t03snap "$g")" "$snap" "旧心跳不得改列"
  vlog "seq1..3 accepted；重放/迟到 accepted=false 且逐列未变"
}

b23() {
  local aref="A-B23-$RANDOM"; local g; g=$(seed_gimbal "G-B23-$RANDOM" "$aref" 1)
  gimbal_login "$aref" 1
  hb_op "$G_TOKEN" "$g" "e1" "1"; aeq "$(jget data.accepted)" true "首次"
  local r1; r1=$(psql_b "SELECT status_revision FROM gimbals WHERE id='$g'")
  aeq "$r1" 1 "unknown→online +1"
  hb_op "$G_TOKEN" "$g" "e1" "2"; aeq "$(jget data.accepted)" true "seq2"
  aeq "$(psql_b "SELECT status_revision FROM gimbals WHERE id='$g'")" "$r1" "同状态不递增"
  # Oracle BLOCKER A：epoch 的新旧权威必须来自**服务端验证过的会话代次**，
  # 客户端自填 epoch 字符串不得具备改写权。同一 token（同代次）内换 epoch + 降 seq
  # 是回滚攻击，必须 accepted=false 且逐列未变。
  local snap23; snap23=$(t03snap "$g")
  hb_op "$G_TOKEN" "$g" "e2" "1"; aeq "$(jget data.accepted)" false "同代次换 epoch 降 seq 必须拒绝"
  aeq "$(t03snap "$g")" "$snap23" "被拒心跳不得改任何列"
  aeq "$(psql_b "SELECT status_revision FROM gimbals WHERE id='$g'")" "$r1" "被拒不递增代次"
  # 真实代次推进：DB 递增 credential_version（旧 token 立即失效）→ 重新认证取新 token，
  # 此时新 epoch + 小 seq 才是合法的"新来源会话"，接受并重置基准。
  psql_b "UPDATE gimbals SET credential_version=2 WHERE id='$g'" >/dev/null
  hb_op "$G_TOKEN" "$g" "e3" "9"; aeq "$CODE" 401 "旧代次 token 立即 401"
  gimbal_login "$aref" 2
  hb_op "$G_TOKEN" "$g" "e3" "1"; aeq "$(jget data.accepted)" true "代次推进后新 epoch 小 seq 接受"
  psql_b "UPDATE gimbals SET connection_status='offline' WHERE id='$g'" >/dev/null
  hb_op "$G_TOKEN" "$g" "e3" "2"; aeq "$(jget data.accepted)" true "offline→online"
  aeq "$(psql_b "SELECT status_revision FROM gimbals WHERE id='$g'")" $((r1+1)) "offline→online +1"
  vlog "同代次换 epoch 降 seq 拒绝且逐列未变；代次推进后新 epoch 接受；unknown/offline→online +1；同状态不递增"
}

b24() {
  local aref="A-B24-$RANDOM"; local g; g=$(seed_gimbal "G-B24-$RANDOM" "$aref" 1)
  gimbal_login "$aref" 1
  local rep='[{"code":"overheat","severity":"high"}]'
  local i
  for i in 1 2 3; do hb_op "$G_TOKEN" "$g" "e1" "$i" "$rep"; aeq "$CODE" 200 "hb $i"; done
  aeq "$(psql_b "SELECT count(*) FROM gimbals g, jsonb_each(g.active_incidents->'episodes') e WHERE g.id='$g' AND e.value->>'code'='overheat' AND e.value->>'state'='active'")" 1 "同一 episode 只 1 个"
  local iid; iid=$(psql_b "SELECT e.key FROM gimbals g, jsonb_each(g.active_incidents->'episodes') e WHERE g.id='$g' AND e.value->>'state'='active' LIMIT 1")
  hb_op "$G_TOKEN" "$g" "e1" "4" '[{"code":"overheat","state":"cleared"}]'
  aeq "$(psql_b "SELECT e.value->>'state' FROM gimbals g, jsonb_each(g.active_incidents->'episodes') e WHERE g.id='$g' AND e.key='$iid'")" resolved "resolved"
  [[ -n "$(psql_b "SELECT e.value->>'resolved_at' FROM gimbals g, jsonb_each(g.active_incidents->'episodes') e WHERE g.id='$g' AND e.key='$iid'")" ]] || fail "缺 resolved_at"
  hb_op "$G_TOKEN" "$g" "e1" "5" "$rep"
  local iid2; iid2=$(psql_b "SELECT e.key FROM gimbals g, jsonb_each(g.active_incidents->'episodes') e WHERE g.id='$g' AND e.value->>'state'='active' LIMIT 1")
  aneq "$iid2" "$iid" "清除后再报应新 incidentId"
  vlog "同 code 复用 episode；清除 resolved+resolved_at；再报新 id"
}

b25() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  scanner_once > "$TMP/b25.scan1.json" || fail "scanner1"
  local nid; nid=$(psql_b "SELECT id FROM notifications WHERE gimbal_id='$g' AND incident_id='$inc' LIMIT 1")
  [[ -n "$nid" ]] || fail "scanner 未建 T10"
  start_worker transient not_found b25
  local i cnt=0
  for i in $(seq 1 60); do
    cnt=$(psql_b "SELECT count(*) FROM async_jobs WHERE owner_id='$nid' AND status='queued' AND attempt_count>=1")
    [[ "$cnt" == 1 ]] && break
    sleep 0.5
  done
  aeq "$cnt" 1 "transient 后 T12 回 queued"
  stop_worker
  aeq "$(psql_b "SELECT status FROM async_jobs WHERE owner_id='$nid'")" queued "SIGTERM 后任务未丢"
  psql_b "UPDATE async_jobs SET status='running',lease_owner='ghost',lease_until=now()-interval '1 hour' WHERE owner_id='$nid'" >/dev/null
  start_worker accepted accepted b25b
  local st="" t10=""
  for i in $(seq 1 80); do
    st=$(psql_b "SELECT status FROM async_jobs WHERE owner_id='$nid'")
    t10=$(psql_b "SELECT status FROM notifications WHERE id='$nid'")
    [[ "$st" == succeeded && "$t10" == submitted ]] && break
    sleep 0.5
  done
  stop_worker
  aeq "$st" succeeded "重启后 T12 收敛 succeeded"
  aeq "$t10" submitted "T10 收敛 submitted"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE id='$nid' AND provider_message_id IS NOT NULL")" 1 "provider_message_id 仅 1"
  aeq "$(psql_b "SELECT count(*) FROM async_jobs WHERE owner_id='$nid'")" 1 "无重复 T12"
  vlog "SIGTERM 后任务保留；租约过期回收；重启收敛 submitted；无重复 T12"
}

b26() {
  local before after
  before=$(psql_b "SELECT id::text||':'||coalesce(last_seen_at::text,'NULL') FROM gimbals ORDER BY id")
  scanner_once > "$TMP/b26.scan.json" || fail "scanner"
  after=$(psql_b "SELECT id::text||':'||coalesce(last_seen_at::text,'NULL') FROM gimbals ORDER BY id")
  aeq "$after" "$before" "扫描前后 last_seen_at 快照逐字节一致"
  local src="$WORKERPY/src/mvp_worker/scanners/incident_scanner.py"
  grep -n "UPDATE[[:space:]]*gimbals" "$src" > "$TMP/b26.updates" || true
  [[ -s "$TMP/b26.updates" ]] || fail "未找到 gimbals UPDATE（源码结构变化？）"
  if grep -Eq "SET[^;]*last_seen_at|,[[:space:]]*last_seen_at[[:space:]]*=" "$src"; then
    fail "扫描器源码中出现 last_seen_at 赋值"
  fi
  grep -q "connection_status" "$src" || fail "扫描器未写 connection_status"
  vlog "SQL 快照一致；扫描器源码无 last_seen_at 写法（UPDATE 行：$(tr '\n' ';' < "$TMP/b26.updates")）"
}
