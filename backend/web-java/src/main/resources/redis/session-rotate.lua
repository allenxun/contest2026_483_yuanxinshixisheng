-- refresh 轮换（CAS）：校验旧会话仍存在 → 删旧 → 建新，全部在同一原子步完成。
-- 调用方只做**只读**领取（GET rtKey），本脚本负责"校验 + 消费 refresh + 删旧 + 建新"，
-- 从而在 refresh 与 logout 交错时**不会复活**已撤销的会话（旧 at/sid 已不存在 ⇒ 返回 2）。
-- 所有访问的键均为调用方传入的**具体键名**（无命名空间拼接）。
-- KEYS[1] = 旧 refresh string 键       <prefix>sess:rt:<sha256(oldRefresh)>
-- KEYS[2] = 旧 sessionId 反查 hash 键  <prefix>sess:sid:<oldSessionId>
-- KEYS[3] = 旧 access 会话 hash 键     <prefix>sess:at:<sha256(oldAccess)>
-- KEYS[4] = 新 access 会话 hash 键     <prefix>sess:at:<sha256(newAccess)>
-- KEYS[5] = 新 sessionId 反查 hash 键  <prefix>sess:sid:<newSessionId>
-- KEYS[6] = 新 refresh string 键       <prefix>sess:rt:<sha256(newRefresh)>
-- ARGV[1]  = expectedSid  旧 sessionId（必须等于 rtKey 当前值）
-- ARGV[2]  = ttlSeconds
-- ARGV[3]  = kind（恒为 app）
-- ARGV[4]  = newSessionId
-- ARGV[5]  = aid
-- ARGV[6]  = iid
-- ARGV[7]  = rev          （沿用旧会话的 revision 快照）
-- ARGV[8]  = iat
-- ARGV[9]  = exp
-- ARGV[10] = newAtDigest  sha256(newAccess)
-- ARGV[11] = newRtDigest  sha256(newRefresh)
-- 返回码：1=轮换成功；0=refresh 已被消费（并发中另一个赢家/已被用过）；
--         2=会话已被撤销/不存在（旧 sid 或旧 at 缺失）。
-- 顺序不可调换：先 CAS 校验 rt，再校验旧 at/sid 存在，最后才删/建。
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
  return 0
end
if redis.call('EXISTS', KEYS[2]) == 0 then
  return 2
end
if redis.call('EXISTS', KEYS[3]) == 0 then
  return 2
end
redis.call('DEL', KEYS[1])
redis.call('DEL', KEYS[2])
redis.call('DEL', KEYS[3])
redis.call('HSET', KEYS[4], 'kind', ARGV[3], 'sid', ARGV[4], 'aid', ARGV[5],
           'iid', ARGV[6], 'rev', ARGV[7], 'iat', ARGV[8], 'exp', ARGV[9], 'rt', ARGV[11])
redis.call('EXPIRE', KEYS[4], ARGV[2])
redis.call('HSET', KEYS[5], 'at', ARGV[10], 'rt', ARGV[11])
redis.call('EXPIRE', KEYS[5], ARGV[2])
redis.call('SET', KEYS[6], ARGV[4])
redis.call('EXPIRE', KEYS[6], ARGV[2])
return 1
