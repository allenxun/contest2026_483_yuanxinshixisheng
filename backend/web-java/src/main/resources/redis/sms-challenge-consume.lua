-- SMS challenge one-time consumption: expiry check + attempt limit + digest comparison +
-- consumption or failure-counting + returning the phone, all in a SINGLE atomic step.
--
-- KEYS[1] = challenge hash key (<prefix>sms:ch:<challengeId>)
-- ARGV[1] = provided code digest (sha256(code + "|" + challengeId)); a sentinel that can
--           never equal a digest is passed for blank/null input
-- ARGV[2] = now, epoch milliseconds
-- ARGV[3] = max verify attempts
--
-- Returns a STRING (never a Lua boolean):
--   "+<phone>"  successful, one-time consumption (the hash has been deleted)
--   "!"         absent / expired / attempts exhausted / digest mismatch
--
-- The response is never nil and never a boolean, so the Java side can use
-- DefaultRedisScript<String> without the "Lua false -> Redis nil -> Java null" trap.
local key = KEYS[1]
if redis.call('EXISTS', key) == 0 then
  return '!'
end

local expiresAt = tonumber(redis.call('HGET', key, 'exp') or '0')
local now = tonumber(ARGV[2])
if now > expiresAt then
  redis.call('DEL', key)
  return '!'
end

local attempts = tonumber(redis.call('HGET', key, 'att') or '0')
local maxAttempts = tonumber(ARGV[3])
if attempts >= maxAttempts then
  redis.call('DEL', key)
  return '!'
end

local stored = redis.call('HGET', key, 'cd')
if stored ~= ARGV[1] then
  attempts = attempts + 1
  if attempts >= maxAttempts then
    redis.call('DEL', key)
  else
    redis.call('HSET', key, 'att', tostring(attempts))
  end
  return '!'
end

local phone = redis.call('HGET', key, 'ph')
if phone == false then
  redis.call('DEL', key)
  return '!'
end
redis.call('DEL', key)
return '+' .. phone
