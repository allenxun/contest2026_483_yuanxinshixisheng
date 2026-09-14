-- refresh 轮换：删旧 access/sid + 写新 token 对（新 TTL）在同一原子步完成。
-- 旧 refresh 键已由调用方用 GETDEL 原子领取（本脚本不再处理）。
-- 所有访问的键均为调用方传入的**具体键名**（无命名空间拼接）。
-- KEYS[1] = 旧 sessionId 反查 hash 键  <prefix>sess:sid:<oldSessionId>
-- KEYS[2] = 旧 access 会话 hash 键     <prefix>sess:at:<sha256(oldAccess)>
-- KEYS[3] = 新 access 会话 hash 键     <prefix>sess:at:<sha256(newAccess)>
-- KEYS[4] = 新 sessionId 反查 hash 键  <prefix>sess:sid:<newSessionId>
-- KEYS[5] = 新 refresh string 键       <prefix>sess:rt:<sha256(newRefresh)>
-- ARGV[1] = ttlSeconds
-- ARGV[2] = kind（恒为 app）
-- ARGV[3] = newSessionId
-- ARGV[4] = aid
-- ARGV[5] = iid
-- ARGV[6] = rev          （沿用旧会话的 revision 快照）
-- ARGV[7] = iat
-- ARGV[8] = exp
-- ARGV[9] = newAtDigest  sha256(newAccess)
-- ARGV[10] = newRtDigest sha256(newRefresh)
-- 返回 1
redis.call('DEL', KEYS[2])
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[3], 'kind', ARGV[2], 'sid', ARGV[3], 'aid', ARGV[4],
           'iid', ARGV[5], 'rev', ARGV[6], 'iat', ARGV[7], 'exp', ARGV[8], 'rt', ARGV[10])
redis.call('EXPIRE', KEYS[3], ARGV[1])
redis.call('HSET', KEYS[4], 'at', ARGV[9], 'rt', ARGV[10])
redis.call('EXPIRE', KEYS[4], ARGV[1])
redis.call('SET', KEYS[5], ARGV[3])
redis.call('EXPIRE', KEYS[5], ARGV[1])
return 1
