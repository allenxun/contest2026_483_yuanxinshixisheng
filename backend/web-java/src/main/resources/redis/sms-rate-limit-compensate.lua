-- SMS throttle compensation: atomically roll back a reservation made by
-- sms-rate-limit-reserve.lua when the remote send was NOT accepted.
--
-- KEYS[1] = minute window counter key
-- KEYS[2] = hour   window counter key
-- KEYS[3] = day    window counter key
-- ARGV: none
--
-- Returns 1 (integer, never a Lua boolean).
--
-- A key is only decremented when it still exists, so compensation can never create a
-- negative or TTL=-1 counter. When the count reaches zero the key is removed so that the
-- next reservation re-creates it with a fresh TTL.
local function compensate(key)
  if redis.call('EXISTS', key) == 1 then
    local remaining = redis.call('DECR', key)
    if remaining <= 0 then
      redis.call('DEL', key)
    end
  end
end

compensate(KEYS[1])
compensate(KEYS[2])
compensate(KEYS[3])
return 1
