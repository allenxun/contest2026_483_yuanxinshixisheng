-- 创建会话（APP 或 GIMBAL）：多键 + TTL 在同一原子步完成（绝不留下无 TTL 的键）。
-- KEYS[1] = access 会话 hash 键      <prefix>sess:at:<sha256(access)>
-- KEYS[2] = sessionId 反查 hash 键   <prefix>sess:sid:<sessionId>
-- KEYS[3] = refresh string 键        <prefix>sess:rt:<sha256(refresh)>（gimbal 时传 sidKey 占位具体键，不写）
-- ARGV[1] = ttlSeconds
-- ARGV[2] = kind            app | gimbal
-- ARGV[3] = sessionId       原值（不摘要）
-- ARGV[4] = aid             accountId（app）或 gimbalId（gimbal）
-- ARGV[5] = iid             installationId（gimbal 为空串）
-- ARGV[6] = rev             authRevision（app）或 credentialVersion（gimbal）
-- ARGV[7] = iat             epoch millis
-- ARGV[8] = exp             epoch millis
-- ARGV[9] = atDigest        sha256(access)
-- ARGV[10] = rtDigest       sha256(refresh)（gimbal 为空串）
-- ARGV[11] = hasRt          "1" 写 refresh 键，"0" 跳过
-- 返回 1（整数；绝不用 Lua 布尔）
redis.call('HSET', KEYS[1], 'kind', ARGV[2], 'sid', ARGV[3], 'aid', ARGV[4],
           'iid', ARGV[5], 'rev', ARGV[6], 'iat', ARGV[7], 'exp', ARGV[8], 'rt', ARGV[10])
redis.call('EXPIRE', KEYS[1], ARGV[1])
redis.call('HSET', KEYS[2], 'at', ARGV[9], 'rt', ARGV[10])
redis.call('EXPIRE', KEYS[2], ARGV[1])
if ARGV[11] == '1' then
  redis.call('SET', KEYS[3], ARGV[3])
  redis.call('EXPIRE', KEYS[3], ARGV[1])
end
return 1
