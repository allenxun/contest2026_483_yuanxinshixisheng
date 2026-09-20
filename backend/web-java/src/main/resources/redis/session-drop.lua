-- 丢弃一个已知会话（refresh 复核未通过时的连带撤销）。
-- 所有访问的键均为调用方传入的**具体键名**（无命名空间拼接）。
-- KEYS[1] = sessionId 反查 hash 键   <prefix>sess:sid:<sessionId>
-- KEYS[2] = 旧 access 会话 hash 键    <prefix>sess:at:<sha256(access)>
-- KEYS[3] = 旧 refresh string 键      <prefix>sess:rt:<sha256(refresh)>
--           —— 当该会话没有 refresh（摘要为空）时，调用方传入一个**占位具体键**
--           （复用 KEYS[1] 的 sid 键）并置 ARGV[1]='0'，脚本跳过删除，绝不传命名空间/空串。
-- ARGV[1] = hasRefresh  "1" 删 KEYS[3]，"0" 跳过
-- 返回 1
redis.call('DEL', KEYS[2])
redis.call('DEL', KEYS[1])
if ARGV[1] == '1' then
  redis.call('DEL', KEYS[3])
end
return 1
