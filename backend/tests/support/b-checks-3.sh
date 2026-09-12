# shellcheck shell=bash
# B 验收检查定义（组 5/6 + b39/b14 + b40/b41）：b27..b38、b39、b14、b40、b41。
# 由 run-acceptance-b.sh source。

b27() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  scanner_once > "$TMP/b27.scan1.json" || fail "scanner1"
  local nid; nid=$(psql_b "SELECT id FROM notifications WHERE gimbal_id='$g' AND incident_id='$inc' LIMIT 1")
  [[ -n "$nid" ]] || fail "未建 T10"
  worker_once accepted not_found > "$TMP/b27.worker1.log" 2>&1 || { tail -5 "$TMP/b27.worker1.log"; fail "worker1"; }
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid'")" submitted "accepted → submitted"
  [[ -n "$(psql_b "SELECT provider_message_id FROM notifications WHERE id='$nid'")" ]] || fail "缺 provider_message_id"
  local fx2; fx2=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g2 inc2
  g2=$(printf '%s' "$fx2" | $HELP jget gimbalId); inc2=$(printf '%s' "$fx2" | $HELP jget incidentId)
  scanner_once > "$TMP/b27.scan2.json" || fail "scanner2"
  local nid2; nid2=$(psql_b "SELECT id FROM notifications WHERE gimbal_id='$g2' AND incident_id='$inc2' LIMIT 1")
  worker_once delivered not_found > "$TMP/b27.worker2.log" 2>&1 || { tail -5 "$TMP/b27.worker2.log"; fail "worker2"; }
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid2'")" delivered "delivered 模式 → delivered"
  case "$(psql_b "SELECT provider_message_id FROM notifications WHERE id='$nid2'")" in dlv-*) ;; *) fail "delivered provider id 前缀";; esac
  aneq "$(psql_b "SELECT provider_message_id FROM notifications WHERE id='$nid'")" "$(psql_b "SELECT provider_message_id FROM notifications WHERE id='$nid2'")" "submitted≠delivered"
  vlog "scanner→T10+T12→真实 worker：submitted 与 delivered 可区分"
}

b28() {
  local fx; fx=$($FIX episode-gimbal --bound 0 --dest none --episode device)
  local g; g=$(printf '%s' "$fx" | $HELP jget gimbalId)
  scanner_once > "$TMP/b28.scan.json" || fail "scanner"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g'")" 0 "无绑定不建 T10"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g' AND status='submitted'")" 0 "无 submitted"
  grep -q '"skipped_unbound"' "$TMP/b28.scan.json" || fail "scanner 未报告 skipped_unbound"
  grep -Eq '"skipped_unbound":[[:space:]]*[1-9]' "$TMP/b28.scan.json" || fail "skipped_unbound 未计数"
  vlog "无绑定：T10 零行；scanner 记录 skipped_unbound"
}

b29() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest invalid --episode device)
  local g; g=$(printf '%s' "$fx" | $HELP jget gimbalId)
  scanner_once > "$TMP/b29.scan.json" || fail "scanner"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g'")" 0 "无有效目标不建 T10"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g' AND status='submitted'")" 0 "无 submitted"
  grep -Eq '"skipped_no_destination":[[:space:]]*[1-9]' "$TMP/b29.scan.json" || fail "未记录 skipped_no_destination"
  vlog "目标 invalid：T10 零行；记录 skipped_no_destination"
}

b30() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g acct did inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); acct=$(printf '%s' "$fx" | $HELP jget accountId); did=$(printf '%s' "$fx" | $HELP jget destinationId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  local pn; pn=$($FIX pending-notification --gimbal "$g" --account "$acct" --dest "$did" --binding-rev 1 --dest-rev 1 --incident "$inc")
  local nid; nid=$(printf '%s' "$pn" | $HELP jget notificationId)
  $FIX unbind --gimbal "$g" >/dev/null
  start_worker accepted not_found b30
  local st=""
  local i; for i in $(seq 1 40); do st=$(psql_b "SELECT status FROM notifications WHERE id='$nid'"); [[ "$st" == cancelled ]] && break; sleep 0.5; done
  stop_worker
  aeq "$st" cancelled "解绑后重检 cancelled"
  aeq "$(psql_b "SELECT last_error->>'code' FROM notifications WHERE id='$nid'")" route_recheck_failed "last_error.code"
  aeq "$(psql_b "SELECT coalesce(provider_message_id,'NULL') FROM notifications WHERE id='$nid'")" NULL "未发送"
  local pn2; pn2=$($FIX pending-notification --gimbal "$g" --account "$acct" --dest "$did" --binding-rev 1 --dest-rev 1)
  local nid2; nid2=$(printf '%s' "$pn2" | $HELP jget notificationId)
  local out; out=$(env MVP_WORKER_PG_DSN="$B_DSN" $DELIVER "$nid2" --mode accepted)
  aeq "$(printf '%s' "$out" | $HELP jget calls)" 0 "推送调用 0"
  aeq "$(printf '%s' "$out" | $HELP jget status)" cancelled "in-proc cancelled"
  vlog "解绑后 cancelled+route_recheck_failed；推送调用计数 0"
}

b31() {
  local inst="inst-b31-$(new_id|cut -c1-8)"
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device --installation "$inst")
  local g did
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); did=$(printf '%s' "$fx" | $HELP jget destinationId)
  scanner_once > /dev/null || fail "scanner"
  local nid; nid=$(psql_b "SELECT id FROM notifications WHERE gimbal_id='$g' ORDER BY created_at LIMIT 1")
  [[ -n "$nid" ]] || fail "旧通知未建"
  login_app "$(new_phone)" "$inst"
  op_call m5A01RegisterNotificationDestination PUT "$WEB/api/v1/me/notification-destinations/$inst" \
    -H "Authorization: Bearer $APP_TOKEN" -H "Idempotency-Key: k31-$RANDOM" -H 'Content-Type: application/json' \
    -d '{"provider":"dev-fcm","platform":"android","registration":{"token":"t2"},"expectedDestinationRevision":"1"}'
  aeq "$CODE" 200 "换号接管"
  local b_id="$APP_ID"
  aeq "$(psql_b "SELECT account_id FROM notification_destinations WHERE id='$did'")" "$b_id" "目标归 B"
  psql_b "UPDATE gimbals SET bound_account_id='$b_id',binding_revision=2 WHERE id='$g'" >/dev/null
  worker_once accepted not_found > "$TMP/b31.worker.log" 2>&1 || { tail -5 "$TMP/b31.worker.log"; fail "worker"; }
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid'")" cancelled "旧 A 通知 cancelled"
  aeq "$(psql_b "SELECT coalesce(provider_message_id,'NULL') FROM notifications WHERE id='$nid'")" NULL "未向旧目标发送"
  scanner_once > "$TMP/b31.scan2.json" || fail "scanner2"
  local nb; nb=$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g' AND account_id='$b_id'")
  [[ "$nb" -ge 1 ]] || fail "新路由未建通知"
  vlog "换号后旧 A 通知 cancelled 未发送；B 新路由可建通知"
}

b32() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g acct did inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); acct=$(printf '%s' "$fx" | $HELP jget accountId); did=$(printf '%s' "$fx" | $HELP jget destinationId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  local pn; pn=$($FIX pending-notification --gimbal "$g" --account "$acct" --dest "$did" --binding-rev 1 --dest-rev 1 --incident "$inc")
  local nid; nid=$(printf '%s' "$pn" | $HELP jget notificationId)
  worker_once transient not_found > "$TMP/b32.w1.log" 2>&1 || true
  local jobst att
  jobst=$(psql_b "SELECT status FROM async_jobs WHERE owner_id='$nid'"); att=$(psql_b "SELECT attempt_count FROM async_jobs WHERE owner_id='$nid'")
  aeq "$jobst" queued "transient → 退避 queued"; [[ "$att" -ge 1 ]] || fail "attempt_count 未递增"
  local other; other=$(psql_b "INSERT INTO accounts (id,login_provider,login_subject) VALUES (gen_random_uuid(),'phone','o32-$RANDOM') RETURNING id")
  psql_b "UPDATE gimbals SET bound_account_id='$other',binding_revision=2 WHERE id='$g'" >/dev/null
  psql_b "UPDATE async_jobs SET available_at=now() WHERE owner_id='$nid'" >/dev/null
  worker_once accepted not_found > "$TMP/b32.w2.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid'")" cancelled "重试前重检 cancelled"
  aeq "$(psql_b "SELECT coalesce(provider_message_id,'NULL') FROM notifications WHERE id='$nid'")" NULL "未投递"
  aeq "$(psql_b "SELECT last_error->>'reason' FROM notifications WHERE id='$nid'")" binding_changed "reason"
  vlog "transient 退避 queued/attempt+1；改绑后 cancelled 不投递"
}

b33() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g acct did inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); acct=$(printf '%s' "$fx" | $HELP jget accountId); did=$(printf '%s' "$fx" | $HELP jget destinationId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  local pn; pn=$($FIX pending-notification --gimbal "$g" --account "$acct" --dest "$did" --binding-rev 1 --dest-rev 1 --incident "$inc")
  local nid job; nid=$(printf '%s' "$pn" | $HELP jget notificationId); job=$(printf '%s' "$pn" | $HELP jget jobId)
  worker_once unknown not_found > "$TMP/b33.w1.log" 2>&1 || true
  # 语义（总协调 MVP 简化裁定 + Oracle #6 闭合方式）：KIND_UNKNOWN 属**可重试**失败，
  # 非末次尝试**不提前终态化**（不包装 business_tx），T10 保持 sending 可观测态等待
  # 下一次领取对账；只有末次尝试才经 D 的 complete_failure 同事务收敛为终态。
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid'")" sending "非末次 unknown：T10 保持可观测态"
  aeq "$(psql_b "SELECT attempt_count FROM notifications WHERE id='$nid'")" 1 "attempt=1"
  psql_bf <<SQL
UPDATE notifications SET status='sending', attempt_count=1, last_attempt_at=now(), provider_message_id=NULL WHERE id='$nid';
UPDATE async_jobs SET status='queued', available_at=now(), lease_owner=NULL, lease_until=NULL, lease_revision=0, attempt_count=0 WHERE id='$job';
SQL
  worker_once accepted accepted > "$TMP/b33.w2.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid'")" submitted "对账收敛 submitted"
  aeq "$(psql_b "SELECT attempt_count FROM notifications WHERE id='$nid'")" 1 "无第二次投递（attempt 不变）"
  local fx2; fx2=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g2 acct2 did2 inc2
  g2=$(printf '%s' "$fx2" | $HELP jget gimbalId); acct2=$(printf '%s' "$fx2" | $HELP jget accountId); did2=$(printf '%s' "$fx2" | $HELP jget destinationId); inc2=$(printf '%s' "$fx2" | $HELP jget incidentId)
  local pn2; pn2=$($FIX pending-notification --gimbal "$g2" --account "$acct2" --dest "$did2" --binding-rev 1 --dest-rev 1 --incident "$inc2")
  local nid2 job2; nid2=$(printf '%s' "$pn2" | $HELP jget notificationId); job2=$(printf '%s' "$pn2" | $HELP jget jobId)
  psql_bf <<SQL
UPDATE notifications SET status='sending', attempt_count=1, last_attempt_at=now(), provider_message_id=NULL WHERE id='$nid2';
UPDATE async_jobs SET status='queued', available_at=now(), lease_owner=NULL, lease_until=NULL, lease_revision=0, attempt_count=0 WHERE id='$job2';
SQL
  worker_once accepted not_found > "$TMP/b33.w3.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid2'")" submitted "not_found 重发收敛 submitted"
  aeq "$(psql_b "SELECT provider_message_id FROM notifications WHERE id='$nid2'")" "acc-$nid2:1" "同 provider_message_key"
  # Oracle #6 的端到端闭合证据：**末次**尝试的 unknown 必须经 D 的 complete_failure
  # 同事务回调收敛 T10 终态，绝不滞留 sending；且 T10 终态与 T12 failed 同时落库
  # （lease 守卫 0 行时两者整体回滚）。max_attempts=1 使首次尝试即末次。
  local fx3; fx3=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g3 acct3 did3 inc3
  g3=$(printf '%s' "$fx3" | $HELP jget gimbalId); acct3=$(printf '%s' "$fx3" | $HELP jget accountId)
  did3=$(printf '%s' "$fx3" | $HELP jget destinationId); inc3=$(printf '%s' "$fx3" | $HELP jget incidentId)
  local pn3; pn3=$($FIX pending-notification --gimbal "$g3" --account "$acct3" --dest "$did3" \
    --binding-rev 1 --dest-rev 1 --incident "$inc3")
  local nid3 job3
  nid3=$(printf '%s' "$pn3" | $HELP jget notificationId); job3=$(printf '%s' "$pn3" | $HELP jget jobId)
  psql_b "UPDATE async_jobs SET max_attempts=1, attempt_count=0 WHERE id='$job3'" >/dev/null
  worker_once unknown not_found > "$TMP/b33.w4.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid3'")" failed "末次 unknown：T10 同事务收敛 failed（不滞留 sending）"
  aeq "$(psql_b "SELECT status FROM async_jobs WHERE id='$job3'")" failed "T12 同时 failed（同一事务）"
  aeq "$(psql_b "SELECT jsonb_typeof(last_error) FROM notifications WHERE id='$nid3'")" object "T10 留有界 last_error 快照"
  aeq "$(psql_b "SELECT attempt_count FROM notifications WHERE id='$nid3'")" 1 "末次只投递一次，无重复发送"
  vlog "非末次 unknown 保持可观测态不提前终态化；对账收敛 submitted 且 attempt 不变；"
  vlog "not_found 同 key 重发；末次 unknown 经 D 的同事务回调收敛 T10 failed + T12 failed（#6 闭合）"
}

b34() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g acct did inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); acct=$(printf '%s' "$fx" | $HELP jget accountId); did=$(printf '%s' "$fx" | $HELP jget destinationId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  local pn; pn=$($FIX pending-notification --gimbal "$g" --account "$acct" --dest "$did" --binding-rev 1 --dest-rev 1 --incident "$inc")
  local nid; nid=$(printf '%s' "$pn" | $HELP jget notificationId)
  local ptxt; ptxt=$(psql_b "SELECT payload::text FROM notifications WHERE id='$nid'")
  aeq "$(JGET_JSON="$ptxt" $HELP keys)" "event_type,gimbal_id,incident_id,schema_version,text" "payload 键集合"
  JGET_JSON="$ptxt" $HELP jget schema_version >/dev/null
  local bad
  for bad in "$acct" member photo report phone '+86' face; do
    grep -qi -- "$bad" <<<"$ptxt" && fail "payload 含禁止内容 $bad"
  done
  local out; out=$(env MVP_WORKER_PG_DSN="$B_DSN" $DELIVER "$nid" --mode accepted)
  aeq "$(printf '%s' "$out" | $HELP jget calls)" 1 "一次发送"
  local ctext; ctext=$(printf '%s' "$out" | "$CPY" -c 'import json,sys;d=json.load(sys.stdin);print(d["calls_detail"][0]["text"])')
  aeq "$ctext" "云台状态异常，请查看" "推送正文"
  local creg; creg=$(printf '%s' "$out" | "$CPY" -c 'import json,sys;d=json.load(sys.stdin);print(json.dumps(d["calls_detail"][0]["registration"],ensure_ascii=False))')
  for bad in "$acct" member photo report phone '+86' face; do
    grep -qi -- "$bad" <<<"$creg" && fail "推送 registration 含禁止内容 $bad"
  done
  vlog "T10 payload 与推送正文/注册均不含成员/照片/报告/手机号"
}

b35() {
  local fx; fx=$($FIX episode-gimbal --bound 1 --dest active --episode device)
  local g acct did inc
  g=$(printf '%s' "$fx" | $HELP jget gimbalId); acct=$(printf '%s' "$fx" | $HELP jget accountId); did=$(printf '%s' "$fx" | $HELP jget destinationId); inc=$(printf '%s' "$fx" | $HELP jget incidentId)
  local pn; pn=$($FIX pending-notification --gimbal "$g" --account "$acct" --dest "$did" --binding-rev 1 --dest-rev 1 --incident "$inc")
  local nid job; nid=$(printf '%s' "$pn" | $HELP jget notificationId); job=$(printf '%s' "$pn" | $HELP jget jobId)
  local out1; out1=$(env MVP_WORKER_PG_DSN="$B_DSN" $DELIVER "$nid" --mode accepted)
  aeq "$(printf '%s' "$out1" | $HELP jget calls)" 1 "首次投递 1 次"
  aeq "$(printf '%s' "$out1" | $HELP jget status)" submitted "submitted"
  psql_b "UPDATE async_jobs SET status='queued', available_at=now(), lease_owner=NULL, lease_until=NULL, lease_revision=0 WHERE id='$job'" >/dev/null
  local out2; out2=$(env MVP_WORKER_PG_DSN="$B_DSN" $DELIVER "$nid" --mode accepted)
  aeq "$(printf '%s' "$out2" | $HELP jget calls)" 0 "重复领取不再投递"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE id='$nid'")" 1 "无重复 T10"
  scanner_once > /dev/null || fail "scan1"
  local c1; c1=$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g'")
  scanner_once > /dev/null || fail "scan2"
  aeq "$(psql_b "SELECT count(*) FROM notifications WHERE gimbal_id='$g'")" "$c1" "扫描两轮行数不变"
  vlog "同 T12 二次领取 no-op（推送 0）；扫描两轮 T10 行数不变"
}

b36() {
  local out
  out=$(cd "$WEBJAVA" && env -u APP_STORAGE_DEV_DIR "${JAVA_TEST_ENV[@]}" mvn -B test 2>&1) || { printf '%s\n' "$out" | tail -40; fail "mvn test rc!=0"; }
  local line; line=$(printf '%s\n' "$out" | grep -E 'Tests run:.*Failures: [0-9]+, Errors: [0-9]+, Skipped: [0-9]+$' | tail -1)
  [[ -n "$line" ]] || fail "未找到 Tests run 汇总行"
  [[ "$line" == *"Failures: 0, Errors: 0"* ]] || fail "Java 测试失败: $line"
  local n; n=$(printf '%s' "$line" | sed -E 's/.*Tests run: ([0-9]+).*/\1/')
  printf '%s' "$n" > "$TMP/java_tests"
  vlog "Java 合计 $line"
}

b37() {
  local out rc=0
  out=$(cd "$WORKERPY" && env \
    MVP_A_PG_DSN="postgresql://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_PORT}/postgres" \
    MVP_A_PG_CONTAINER="$PG" MVP_A_PG_HOST_PORT="$PG_PORT" \
    MVP_A_PG_USER="$PG_USER" MVP_A_PG_PASSWORD="$PG_PASSWORD" \
    .venv/bin/python -m pytest -q --tb=line 2>&1) || rc=$?
  printf '%s\n' "$out" | tail -25 > "$TMP/b37.tail"
  local summary; summary=$(printf '%s\n' "$out" | grep -E '[0-9]+ (passed|failed|errors?)' | tail -1)
  [[ -n "$summary" ]] || { cat "$TMP/b37.tail"; fail "未找到 pytest 汇总"; }
  local passed failed errors
  passed=$(printf '%s' "$summary" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || true); passed=${passed:-0}
  failed=$(printf '%s' "$summary" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || true); failed=${failed:-0}
  # pytest 汇总把 fixture/收集错误写作 "N errors"（单数时 "N error"），必须显式解析
  errors=$(printf '%s' "$summary" | grep -oE '[0-9]+ errors?' | grep -oE '[0-9]+' | head -1 || true); errors=${errors:-0}
  local bad_lines; bad_lines=$(printf '%s\n' "$out" | grep -E '^(FAILED|ERROR) ' || true)
  # Oracle 第三轮 IMPORTANT：rc 曾被捕获却从未检查、errors 从未解析，导致
  # "200+ passed, 1 error" 会被误报为通过。三项都必须硬断言。
  [[ "$rc" == 0 ]] || { printf '%s\n' "$summary"; printf '%s\n' "$bad_lines"; \
    fail "pytest 退出码=$rc（必须为 0）"; }
  [[ "$failed" == 0 ]] || { printf '%s\n' "$summary"; printf '%s\n' "$bad_lines"; \
    fail "期望 0 个失败，实际 $failed"; }
  [[ "$errors" == 0 ]] || { printf '%s\n' "$summary"; printf '%s\n' "$bad_lines"; \
    fail "期望 0 个 error（fixture/收集错误），实际 $errors"; }
  [[ "$passed" -ge 200 ]] || fail "通过数 $passed < 200"
  vlog "Python passed=$passed failed=$failed errors=$errors rc=$rc"
  vlog "说明：合并集成基线 8afd0e5 后 tests/test_sanity.py 实测 4/4 通过，原 C15 的"
  vlog "环境耦合失败（默认 55432 vs 覆盖 55435）不再复现；本项要求 rc=0 且零 failed、零 error。"
}

b38() {
  local types; types=$($WPY -c "from mvp_worker.handlers import registered_job_types as r; print(','.join(r()))")
  grep -q 'system.echo' <<<"$types" || fail "缺 system.echo：$types"
  grep -q 'notification.deliver' <<<"$types" || fail "缺 notification.deliver：$types"
  local job nid; nid=$(new_id); job=$(new_id)
  psql_bf <<SQL
INSERT INTO async_jobs (id,job_type,dedup_key,owner_type,owner_id,input_revision,payload,status,available_at,attempt_count,max_attempts,lease_revision)
VALUES ('$job','notification.deliver','notification:$nid','notification','$nid',0,CAST('{"schema_version":2,"notification_id":"$nid"}' AS jsonb),'queued',now(),0,5,0);
SQL
  worker_once accepted not_found > "$TMP/b38.w1.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM async_jobs WHERE id='$job'")" failed "契约违规 failed"
  aeq "$(psql_b "SELECT last_error->>'code' FROM async_jobs WHERE id='$job'")" UNSUPPORTED_CONTRACT "code"
  aeq "$(psql_b "SELECT last_error->>'retryable' FROM async_jobs WHERE id='$job'")" false "retryable=false"
  local att; att=$(psql_b "SELECT attempt_count FROM async_jobs WHERE id='$job'")
  worker_once accepted not_found > "$TMP/b38.w2.log" 2>&1 || true
  aeq "$(psql_b "SELECT attempt_count FROM async_jobs WHERE id='$job'")" "$att" "attempt_count 不再增长"
  vlog "注册含 $types；违规 payload → failed/UNSUPPORTED_CONTRACT/retryable=false 不循环"
}

b39() {
  local after; after="$(git -C "$BACKEND/.." status --porcelain 2>/dev/null || true)"
  local head; head=$(git -C "$BACKEND/.." rev-parse HEAD)
  aeq "$head" "$HEAD_BEFORE" "HEAD 未被改动"
  printf '%s\n' "$TREE_BEFORE" > "$TMP/tree.before"
  printf '%s\n' "$after" > "$TMP/tree.after"
  local tracked_before tracked_after
  tracked_before=$(grep -E '^ ?[MADRCTC]' "$TMP/tree.before" | sort || true)
  tracked_after=$(grep -E '^ ?[MADRCTC]' "$TMP/tree.after" | sort || true)
  aeq "$tracked_after" "$tracked_before" "运行不得修改任何 tracked 业务文件"
  local dirty_before dirty_after
  dirty_before=$(printf '%s' "$TREE_BEFORE" | grep -c . || true)
  dirty_after=$(printf '%s' "$after" | grep -c . || true)
  vlog "TREE_BEFORE dirty=$dirty_before · TREE_AFTER dirty=$dirty_after（仅允许未跟踪产物）"
  vlog "tracked 变更 before/after 逐行一致"
}

b14_contract() {
  [[ -s "$OBS_FILE" ]] || fail "无任何错误观测"
  local n=0 viol=0
  while IFS='|' read -r opid code bf; do
    [[ -n "$opid" ]] || continue
    local got; got=$(envelope "$bf") || fail "信封形状非法：$bf"
    if ! $HELP contract-hit "$opid" "$got" >/dev/null 2>&1; then
      local declared; declared=$($HELP contract-list "$opid")
      vlog "CONTRACT-GAP: $opid 观测 $got (HTTP $code) 不在声明集合 {${declared#*=}}"
      viol=$((viol+1))
    fi
    n=$((n+1))
  done < "$OBS_FILE"
  local ops="m1A01CreateMemberAccessGrant m1A02ListMemberAccessGrants m1A03RevokeMemberAccessGrant m2A01CreateGimbalSession m2A02ReportGimbalHeartbeat m2A03GetGimbalStatus m2A04ReportMicrocrystalObservation m2A05GetMicrocrystalCapabilities m2A06BindGimbal m2A07GetGimbalBindingStatus m2A08UnbindGimbal m5A01RegisterNotificationDestination"
  local op
  for op in $ops; do
    grep -q "^$op|" "$OBS_FILE" || fail "端点 $op 未产生任何错误观测"
  done
  vlog "契约驱动：$n 条错误信封形状 OK；12 端点全覆盖"
  [[ $viol -eq 0 ]] || fail "$viol 条观测码不在端点声明集合（见上方 CONTRACT-GAP）"
  vlog "所有观测码均属声明集合"
}

# =====================================================================
# b40 / b41：SC-02-09 真实迟到返回、SC-02-10 确定性终态失败（真实 HTTP + 真实 worker）
# =====================================================================

# 排空「可立即领取」的历史遗留 job（真实 worker_once 消费；不直接改状态）。
b_drain_queue() {
  local i n
  for i in $(seq 1 30); do
    n=$(psql_b "SELECT count(*) FROM async_jobs WHERE status='queued' AND available_at<=now()")
    [[ "$n" == "0" ]] && return 0
    env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev \
      MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" MVP_WORKER_CLAIM_BATCH=5 \
      MVP_WORKER_BACKOFF_BASE_SECONDS=0 MVP_WORKER_BACKOFF_CAP_SECONDS=0 \
      MVP_NOTIFY_PUSH_DOUBLE=accepted MVP_NOTIFY_PUSH_RECEIPT=not_found \
      "$WPY" -m mvp_worker --once >/dev/null 2>&1 || true
  done
  return 0
}

# M3-A01 multipart：b_a01_upload <token> <idem> <front> <left> <right> <capture> <consent>
b_a01_upload() {
  local tok="$1" key="$2" front="$3" left="$4" right="$5" cap="$6" consent="$7"
  local meta="$TMP/b40.a01.meta"
  printf '{"photoVersion":"1","captureSessionId":"%s","consentEvidenceRef":"%s"}' \
    "$cap" "$consent" > "$meta"
  call POST "$WEB/api/v1/skin-assessment-tasks" \
    -H "Authorization: Bearer $tok" -H "Idempotency-Key: $key" \
    -F "metadata=@$meta;type=application/json" \
    -F "front=@$front;type=image/png" \
    -F "left=@$left;type=image/png" \
    -F "right=@$right;type=image/png"
}

# M3-A02 multipart：b_a02_upload <token> <idem> <taskId> <new-front> <expectedVersion>
b_a02_upload() {
  local tok="$1" key="$2" tid="$3" front="$4" expected="$5"
  local meta="$TMP/b40.a02.meta"
  printf '{"expectedPhotoVersion":"%s","replacedViews":["front"]}' "$expected" > "$meta"
  call PUT "$WEB/api/v1/skin-assessment-tasks/$tid/photo-versions/2" \
    -H "Authorization: Bearer $tok" -H "Idempotency-Key: $key" \
    -F "metadata=@$meta;type=application/json" -F "front=@$front;type=image/png"
}

b40_wait_file() { # <file> <seconds>
  local i n=$(( $2 * 4 ))
  for i in $(seq 1 "$n"); do [[ -e "$1" ]] && return 0; sleep 0.25; done
  return 1
}

# 后台 Worker A：barrier hold；短租约、长续租间隔（不关闭续租机制）
b40_start_a() { # <barrier-dir> <marker-sha256>
  nohup env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev \
    MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" \
    MVP_WORKER_CLAIM_BATCH=1 MVP_WORKER_LEASE_SECONDS=2 MVP_WORKER_RENEW_INTERVAL_SECONDS=600 \
    MVP_D_DOUBLE_LATE_BARRIER=true \
    MVP_D_DOUBLE_LATE_BARRIER_DIR="$1" \
    MVP_D_DOUBLE_LATE_BARRIER_SHA256="$2" \
    MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS=180 \
    "$WPY" -m mvp_worker --once >"$TMP/b40a.log" 2>&1 &
  echo $! > "$TMP/b40a.pid"
}

b40_stop_a() {
  [[ -f "$TMP/b40a.pid" ]] || return 0
  local pid; pid=$(cat "$TMP/b40a.pid" 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
    local i; for i in $(seq 1 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$TMP/b40a.pid"
}

b40() {
  local bdir="$TMP/b40-barrier"
  rm -rf "$bdir"; mkdir -p "$bdir"
  b_drain_queue

  # 1) 含可识别标记的照片（标记 = front 字节 sha256）
  make_face "$TMP/b40.front" "b40-marker-$RANDOM"
  make_face "$TMP/b40.left" "b40-left-$RANDOM"
  make_face "$TMP/b40.right" "b40-right-$RANDOM"
  local marker; marker=$($HELP sha256 "$TMP/b40.front")
  [[ "${#marker}" == 64 ]] || fail "marker sha256 形态非法"

  # 2) 真实 HTTP M3-A01 → J1(rev=1)
  local aref="A-B40-$RANDOM"; seed_gimbal "G-B40-$RANDOM" "$aref" 1 >/dev/null
  gimbal_login "$aref" 1
  b_a01_upload "$G_TOKEN" "k40-a01-$RANDOM" "$TMP/b40.front" "$TMP/b40.left" "$TMP/b40.right" "cs-b40" "consent-b40"
  aeq "$CODE" 202 "M3-A01 202"
  local tid; tid=$(jget data.taskId) || fail "no taskId"
  aeq "$(jget data.status)" queued "A01 status"
  aeq "$(psql_b "SELECT current_photo_version FROM skin_assessments WHERE id='$tid'")" 1 "v1"
  aeq "$(psql_b "SELECT processing_revision FROM skin_assessments WHERE id='$tid'")" 1 "rev=1"
  aeq "$(psql_b "SELECT lease_revision FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" 0 "J1 入队 rev=0"

  # 3) 后台 Worker A（barrier hold）
  b40_start_a "$bdir" "$marker"

  # 4) 等 consumed：A 已算出旧结果并阻塞
  b40_wait_file "$bdir/consumed" 60 || { tail -n 20 "$TMP/b40a.log"; fail "A 未进入 barrier"; }
  local rev_hold owner_hold att_hold st_hold
  st_hold=$(psql_b "SELECT status FROM skin_assessments WHERE id='$tid'")
  rev_hold=$(psql_b "SELECT lease_revision FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")
  owner_hold=$(psql_b "SELECT coalesce(lease_owner,'NULL') FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")
  att_hold=$(psql_b "SELECT attempt_count FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")
  aeq "$st_hold" analyzing "A 已置 analyzing"
  aeq "$att_hold" 1 "A 首次领取 attempt=1"
  [[ "$owner_hold" != NULL ]] || fail "A hold 时应有 lease_owner"
  vlog "A hold: T05=$st_hold rev=$rev_hold attempt=$att_hold"

  # 5) 短租约自然过期 → 真实回收 → J1 回 queued 且 rev 推进
  sleep 2.5
  env MVP_WORKER_PG_DSN="$B_DSN" "$WPY" -m mvp_worker --recover > "$TMP/b40.recover.log" 2>&1 || fail "recover rc"
  local rev_rec
  rev_rec=$(psql_b "SELECT lease_revision FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")
  aeq "$(psql_b "SELECT status FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" queued "回收→queued"
  aeq "$(psql_b "SELECT coalesce(lease_owner,'NULL') FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" NULL "回收清 owner"
  [[ "$rev_rec" -gt "$rev_hold" ]] || fail "回收未推进 lease_revision ($rev_hold→$rev_rec)"
  vlog "recover: J1 queued rev=$rev_hold→$rev_rec"

  # 6) Worker B 接管（同 barrier env → 证明一次性，B 不被阻塞）
  env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev \
    MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" MVP_WORKER_CLAIM_BATCH=1 \
    MVP_D_DOUBLE_LATE_BARRIER=true \
    MVP_D_DOUBLE_LATE_BARRIER_DIR="$bdir" \
    MVP_D_DOUBLE_LATE_BARRIER_SHA256="$marker" \
    MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS=180 \
    MVP_D_FACE_DOUBLE_QUALITY=needs_retake MVP_D_FACE_DOUBLE_REQUIRED_VIEWS=front \
    "$WPY" -m mvp_worker --once > "$TMP/b40.workerB.log" 2>&1 || { tail -n 10 "$TMP/b40.workerB.log"; fail "B rc"; }
  aeq "$(psql_b "SELECT status FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" succeeded "B 接管 succeeded"
  aeq "$(psql_b "SELECT attempt_count FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" 2 "接管 attempt=2"
  aeq "$(psql_b "SELECT status FROM skin_assessments WHERE id='$tid'")" needs_retake "B 提交 needs_retake"
  vlog "B takeover: J1 succeeded attempt=2; T05 needs_retake"

  # 7) 真实 HTTP M3-A02 补拍 v2
  make_face "$TMP/b40v2.front" "b40-v2-$RANDOM"
  b_a02_upload "$G_TOKEN" "k40-a02-$RANDOM" "$tid" "$TMP/b40v2.front" 1
  aeq "$CODE" 202 "M3-A02 202"
  aeq "$(jget data.photoVersion)" 2 "A02 photoVersion=2"
  aeq "$(psql_b "SELECT current_photo_version FROM skin_assessments WHERE id='$tid'")" 2 "v2"
  aeq "$(psql_b "SELECT processing_revision FROM skin_assessments WHERE id='$tid'")" 2 "rev=2"
  aeq "$(psql_b "SELECT count(*) FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze' AND input_revision=2")" 1 "J2 入队"
  vlog "A02: v2 rev=2; J2 入队"

  # 8) Worker C 正常 env 跑到 report_ready（有界循环）
  local i st
  for i in $(seq 1 60); do
    st=$(psql_b "SELECT status FROM skin_assessments WHERE id='$tid'")
    [[ "$st" == report_ready ]] && break
    env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev \
      MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" MVP_WORKER_CLAIM_BATCH=5 \
      MVP_WORKER_BACKOFF_BASE_SECONDS=0 MVP_WORKER_BACKOFF_CAP_SECONDS=0 \
      MVP_NOTIFY_PUSH_DOUBLE=accepted MVP_NOTIFY_PUSH_RECEIPT=not_found \
      "$WPY" -m mvp_worker --once > "$TMP/b40.workerC.$i.log" 2>&1 || true
    sleep 0.4
  done
  aeq "$st" report_ready "C 到达 report_ready"
  aeq "$(psql_b "SELECT report_photo_version FROM skin_assessments WHERE id='$tid'")" 2 "report_photo_version=2"
  local snap_rid snap_payload snap_summary snap_member members_before
  snap_rid=$(psql_b "SELECT report_id::text FROM skin_assessments WHERE id='$tid'")
  snap_payload=$(psql_b "SELECT coalesce(report_payload::text,'NULL') FROM skin_assessments WHERE id='$tid'")
  snap_summary=$(psql_b "SELECT coalesce(report_summary::text,'NULL') FROM skin_assessments WHERE id='$tid'")
  snap_member=$(psql_b "SELECT coalesce(member_id::text,'NULL') FROM skin_assessments WHERE id='$tid'")
  members_before=$(psql_b "SELECT count(*) FROM members")
  [[ -n "$snap_rid" ]] || fail "v2 report_id 为空"
  vlog "C: report_ready v2 rid=${snap_rid:0:8}… member=${snap_member:0:8}…"

  # 9) 释放 A 的迟到旧结果 → 既有围栏拒绝 → v2 快照逐值不变
  : > "$bdir/released"
  wait "$(cat "$TMP/b40a.pid")" 2>/dev/null || true
  local i2; for i2 in $(seq 1 40); do
    kill -0 "$(cat "$TMP/b40a.pid" 2>/dev/null || echo 0)" 2>/dev/null || break; sleep 0.25
  done
  grep -qE 'job.complete_stale_generation|analyze.fenced_write_stale|StaleGeneration' "$TMP/b40a.log" \
    || { tail -n 25 "$TMP/b40a.log"; fail "A 无 StaleGeneration 围栏丢弃证据"; }
  local fence_line; fence_line=$(grep -E 'job.complete_stale_generation|analyze.fenced_write_stale|StaleGeneration' "$TMP/b40a.log" | tail -n 1 || true)
  vlog "A fence: ${fence_line:0:240}"
  b40_stop_a

  aeq "$(psql_b "SELECT report_id::text FROM skin_assessments WHERE id='$tid'")" "$snap_rid" "A 未覆盖 report_id"
  aeq "$(psql_b "SELECT coalesce(report_payload::text,'NULL') FROM skin_assessments WHERE id='$tid'")" "$snap_payload" "A 未覆盖 report_payload"
  aeq "$(psql_b "SELECT coalesce(report_summary::text,'NULL') FROM skin_assessments WHERE id='$tid'")" "$snap_summary" "A 未覆盖 report_summary"
  aeq "$(psql_b "SELECT coalesce(member_id::text,'NULL') FROM skin_assessments WHERE id='$tid'")" "$snap_member" "A 未覆盖 member_id"
  aeq "$(psql_b "SELECT report_photo_version FROM skin_assessments WHERE id='$tid'")" 2 "report_photo_version 仍 2"
  aeq "$(psql_b "SELECT count(*) FROM skin_assessments WHERE id='$tid' AND status='report_ready'")" 1 "恰一份 report_ready"
  aeq "$(psql_b "SELECT count(*) FROM members")" "$members_before" "A 未创建额外成员"
  # 该云台恰一行 T05（A 未新建第二行；全库可能含其它检查的 T05，故按 gimbal 收窄）
  aeq "$(psql_b "SELECT count(*) FROM skin_assessments WHERE gimbal_id='$G_ID'")" 1 "该云台仅一行 T05"
  aeq "$(psql_b "SELECT count(*) FROM skin_assessments WHERE id='$tid'")" 1 "taskId 唯一 T05 行"
  [[ ! -e "$bdir/consumed" && ! -e "$bdir/released" ]] || fail "barrier 有残留 sentinel"
  vlog "A 被围栏丢弃；v2 快照逐值未变；report_ready=1；members 不变；sentinel 已清理"
}

b41() {
  b_drain_queue
  local aref="A-B41-$RANDOM"; seed_gimbal "G-B41-$RANDOM" "$aref" 1 >/dev/null
  gimbal_login "$aref" 1
  make_face "$TMP/b41.front" "b41-$RANDOM"
  make_face "$TMP/b41.left" "b41-left-$RANDOM"
  make_face "$TMP/b41.right" "b41-right-$RANDOM"
  b_a01_upload "$G_TOKEN" "k41-a01-$RANDOM" "$TMP/b41.front" "$TMP/b41.left" "$TMP/b41.right" "cs-b41" "consent-b41"
  aeq "$CODE" 202 "M3-A01 202"
  local tid; tid=$(jget data.taskId) || fail "no taskId"

  # 2) 1 轮确定性终态失败（既有 PROVIDER_CONTRACT_VIOLATION）
  env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev \
    MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" MVP_WORKER_CLAIM_BATCH=1 \
    MVP_D_SKIN_DOUBLE_INVALID=out_of_range \
    "$WPY" -m mvp_worker --once > "$TMP/b41.w1.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM skin_assessments WHERE id='$tid'")" failed "T05 failed"
  aeq "$(psql_b "SELECT failure_code FROM skin_assessments WHERE id='$tid'")" PROVIDER_CONTRACT_VIOLATION "failure_code"
  [[ -n "$(psql_b "SELECT coalesce(failure_detail->>'reason','') FROM skin_assessments WHERE id='$tid'")" ]] || fail "failure_detail.reason 空"
  aeq "$(psql_b "SELECT coalesce(report_id::text,'NULL') FROM skin_assessments WHERE id='$tid'")" NULL "report_id null"
  aeq "$(psql_b "SELECT coalesce(report_payload::text,'NULL') FROM skin_assessments WHERE id='$tid'")" NULL "report_payload null"
  aeq "$(psql_b "SELECT status FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" failed "T12 failed"
  aeq "$(psql_b "SELECT attempt_count FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" 1 "attempt=1"
  aeq "$(psql_b "SELECT last_error->>'retryable' FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" false "retryable=false"
  aeq "$(psql_b "SELECT count(*) FROM async_jobs WHERE owner_id='$tid'")" 1 "无后继 job"
  vlog "failure_detail.reason=$(psql_b "SELECT coalesce(failure_detail->>'reason','') FROM skin_assessments WHERE id='$tid'")"
  vlog "T12 last_error=$(psql_b "SELECT last_error::text FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")"
  vlog "T05 failed/PROVIDER_CONTRACT_VIOLATION；attempt=1；无后继 job"

  # 3) M3-A03 投影一致 + 不外泄 + 查询无副作用
  local jobs_before; jobs_before=$(psql_b "SELECT count(*) FROM async_jobs WHERE owner_id='$tid'")
  call GET "$WEB/api/v1/skin-assessment-tasks/$tid" -H "Authorization: Bearer $G_TOKEN"
  aeq "$CODE" 200 "M3-A03 200"
  aeq "$(jget data.status)" failed "A03 status"
  aeq "$(jget data.failureCode)" PROVIDER_CONTRACT_VIOLATION "A03 failureCode"
  aeq "$(jget data.retryable)" false "A03 retryable"
  aeq "$(jget data.reportId)" null "A03 reportId null"
  grep -qE 'failure_detail|failureDetail|"reason"|stack' <<<"$BODY" && fail "A03 泄漏内部诊断"
  aeq "$(psql_b "SELECT count(*) FROM async_jobs WHERE owner_id='$tid'")" "$jobs_before" "GET 不新增 job"
  vlog "A03 投影：status=$(jget data.status) failureCode=$(jget data.failureCode) retryable=$(jget data.retryable) reportId=$(jget data.reportId) requiredViews=$(jget data.requiredViews)"
  vlog "A03 无内部诊断泄漏；GET 不新增 job（before/after=$jobs_before）"

  # 4) 再跑一次仍终态、attempt 不增长
  local att2; att2=$(psql_b "SELECT attempt_count FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")
  env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" \
    MVP_WORKER_CLAIM_BATCH=1 MVP_D_SKIN_DOUBLE_INVALID=out_of_range \
    "$WPY" -m mvp_worker --once > "$TMP/b41.w2.log" 2>&1 || true
  aeq "$(psql_b "SELECT status FROM skin_assessments WHERE id='$tid'")" failed "仍 failed"
  aeq "$(psql_b "SELECT attempt_count FROM async_jobs WHERE owner_id='$tid' AND job_type='assessment.analyze'")" "$att2" "attempt 不增长"

  # 5) 对照：复位后同一流程可正常到达 report_ready（证明失败受控）
  local aref2="A-B41C-$RANDOM"; seed_gimbal "G-B41C-$RANDOM" "$aref2" 1 >/dev/null
  gimbal_login "$aref2" 1
  b_a01_upload "$G_TOKEN" "k41c-a01-$RANDOM" "$TMP/b41.front" "$TMP/b41.left" "$TMP/b41.right" "cs-b41c" "consent-b41c"
  aeq "$CODE" 202 "对照 A01 202"
  local tid2; tid2=$(jget data.taskId) || fail "no tid2"
  local i st
  for i in $(seq 1 60); do
    st=$(psql_b "SELECT status FROM skin_assessments WHERE id='$tid2'")
    [[ "$st" == report_ready ]] && break
    env MVP_WORKER_PG_DSN="$B_DSN" MVP_NOTIFY_ENV=dev MVP_A_STORAGE_DEV_DIR="$STORAGE_ROOT" \
      MVP_WORKER_CLAIM_BATCH=5 MVP_WORKER_BACKOFF_BASE_SECONDS=0 MVP_WORKER_BACKOFF_CAP_SECONDS=0 \
      MVP_NOTIFY_PUSH_DOUBLE=accepted MVP_NOTIFY_PUSH_RECEIPT=not_found \
      "$WPY" -m mvp_worker --once > "$TMP/b41.c.$i.log" 2>&1 || true
    sleep 0.4
  done
  aeq "$st" report_ready "复位对照 report_ready"
  vlog "确定性终态失败（1 轮）；A03 投影一致/无泄漏/无副作用；复位后可达 report_ready"
}
