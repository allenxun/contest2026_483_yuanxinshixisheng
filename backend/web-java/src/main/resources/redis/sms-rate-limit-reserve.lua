-- SMS throttle: atomic "check three UTC+8 natural windows, reserve all-or-nothing".
--
-- KEYS[1] = minute window counter key (<prefix>sms:rl:<sha256(phone)>:m:<yyyyMMddHHmm>)
-- KEYS[2] = hour   window counter key (<prefix>sms:rl:<sha256(phone)>:h:<yyyyMMddHH>)
-- KEYS[3] = day    window counter key (<prefix>sms:rl:<sha256(phone)>:d:<yyyyMMdd>)
--
-- ARGV[1] = max sends per minute
-- ARGV[2] = max sends per hour
-- ARGV[3] = max sends per day
-- ARGV[4] = TTL seconds for the minute key (window remainder + skew margin)
-- ARGV[5] = TTL seconds for the hour key
-- ARGV[6] = TTL seconds for the day key
-- ARGV[7] = retry-after seconds when the minute window is exhausted
-- ARGV[8] = retry-after seconds when the hour window is exhausted
-- ARGV[9] = retry-after seconds when the day window is exhausted
--
-- Returns 0 when all three windows were reserved; otherwise the retry-after seconds
-- (a positive integer, never a Lua boolean) for the most severe exhausted window.
--
-- Atomicity discipline: the counter increment and its EXPIRE happen in the SAME script,
-- so a crash can never leave a TTL=-1 (never-expiring) counter. A bare INCR followed by a
-- separate EXPIRE is a two-command sequence and does not close that window.
local maxMinute = tonumber(ARGV[1])
local maxHour = tonumber(ARGV[2])
local maxDay = tonumber(ARGV[3])
local ttlMinute = tonumber(ARGV[4])
local ttlHour = tonumber(ARGV[5])
local ttlDay = tonumber(ARGV[6])
local retryMinute = tonumber(ARGV[7])
local retryHour = tonumber(ARGV[8])
local retryDay = tonumber(ARGV[9])

local minute = tonumber(redis.call('GET', KEYS[1]) or '0')
local hour = tonumber(redis.call('GET', KEYS[2]) or '0')
local day = tonumber(redis.call('GET', KEYS[3]) or '0')

local retry = 0
if minute >= maxMinute then
  retry = math.max(retry, retryMinute)
end
if hour >= maxHour then
  retry = math.max(retry, retryHour)
end
if day >= maxDay then
  retry = math.max(retry, retryDay)
end
if retry > 0 then
  return retry
end

local function reserve(key, ttl)
  local count = redis.call('INCR', key)
  if count == 1 then
    redis.call('EXPIRE', key, ttl)
  end
end

reserve(KEYS[1], ttlMinute)
reserve(KEYS[2], ttlHour)
reserve(KEYS[3], ttlDay)
return 0
