# shellcheck shell=bash
# B 验收检查定义（组 5/6 + b39/b14）：b27..b38、b39、b14。由 run-acceptance-b.sh source。

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
  aeq "$(psql_b "SELECT status FROM notifications WHERE id='$nid'")" unknown "首次 unknown"
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
  vlog "unknown 不重发；崩溃对账 submitted（attempt 不变）；not_found 同 key 重发"
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
  local summary; summary=$(printf '%s\n' "$out" | grep -E '[0-9]+ (passed|failed)' | tail -1)
  [[ -n "$summary" ]] || { cat "$TMP/b37.tail"; fail "未找到 pytest 汇总"; }
  local passed failed
  passed=$(printf '%s' "$summary" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || true); passed=${passed:-0}
  failed=$(printf '%s' "$summary" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || true); failed=${failed:-0}
  local failed_lines; failed_lines=$(printf '%s\n' "$out" | grep -E '^FAILED ' || true)
  [[ "$failed" == 1 ]] || { printf '%s\n' "$summary"; fail "期望恰好 1 个失败（披露的 A 断言），实际 $failed"; }
  grep -q 'tests/test_sanity.py::test_config_defaults' <<<"$failed_lines" \
    || { printf '%s\n' "$failed_lines"; fail "唯一失败不是 test_config_defaults"; }
  [[ "$passed" -ge 75 ]] || fail "通过数 $passed < 75"
  vlog "Python passed=$passed failed=1；唯一失败=tests/test_sanity.py::test_config_defaults"
  vlog "分类：DISCLOSED ENV-COUPLED A ASSERTION（默认 55432 vs 覆盖 55435），非 B 缺陷；其余全部通过"
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
