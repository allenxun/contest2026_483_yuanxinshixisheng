-- 撤销（logout）：HGETALL + DEL 全部键在同一原子步完成 ⇒ 并发登出恰好一个赢家。
-- 与 rotate/drop 不同，本脚本需要删除的 sess:sid:* / sess:rt:* 键名依赖脚本内 HGETALL 读到的
-- sid / rt 摘要，调用方在脚本执行前**无法知道**；而"读取 + 删除"必须原子才能保证恰好一次，
-- 因此这是**结构性不可避免**的：KEYS[2]/KEYS[3] 传命名空间（<prefix>sess:sid: / <prefix>sess:rt:），
-- 由脚本拼接运行期读到的摘要。
--   * standalone：正确（本地/根当前部署即此形态）。
--   * cluster：**不成立** —— 官方要求脚本访问的所有键必须显式声明于 KEYS[] 且落在同一 hash slot。
-- 具体可行的 cluster 迁移路径（本轮不实现）：
--   1) sess:at:<digest> 只存 sessionId（access→sid 的索引）；
--   2) 会话数据集中到带 hash tag 的单键 sess:{<sessionId>}（同一 slot）；
--   3) 撤销改为两步：先 GETDEL sess:at:<digest> → sid 保证**恰好一次**（赢家唯一），
--      再以完整 KEYS[] 声明（sess:{sid}、sess:{sid}:rt:<digest> 等全部带同一 hash tag）执行第二个脚本。
-- KEYS[1] = access 会话 hash 键  <prefix>sess:at:<sha256(access)>（由调用方具体给出）
-- KEYS[2] = sessionId 命名空间   <prefix>sess:sid:
-- KEYS[3] = refresh 命名空间     <prefix>sess:rt:
-- 返回 table：命中时 {sid, kind, aid, iid}；未命中（已被并发赢家取走/不存在）时 {}
--   （绝不用 Lua 布尔；table 元素为字符串）
local h = redis.call('HGETALL', KEYS[1])
if #h == 0 then
  return {}
end
local m = {}
for i = 1, #h, 2 do
  m[h[i]] = h[i + 1]
end
redis.call('DEL', KEYS[1])
local sid = m['sid']
local rt = m['rt']
if sid then
  redis.call('DEL', KEYS[2] .. sid)
end
if rt and #rt > 0 then
  redis.call('DEL', KEYS[3] .. rt)
end
return {sid or '', m['kind'] or '', m['aid'] or '', m['iid'] or ''}
