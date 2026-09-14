-- SMS challenge creation: write the challenge hash and its TTL in one atomic step,
-- only if the challenge does not already exist.
--
-- KEYS[1] = challenge hash key (<prefix>sms:ch:<challengeId>)
-- ARGV[1] = stored code digest (sha256(code + "|" + challengeId)); the plaintext code is
--           NEVER written to Redis
-- ARGV[2] = phone number (the only PII in the value; value-only, never a key)
-- ARGV[3] = expires-at, epoch milliseconds
-- ARGV[4] = TTL seconds (challenge-ttl-seconds; the attempt counter lives in this same hash
--           field 'att', so it shares the key TTL and can never become a TTL=-1 orphan)
--
-- Returns 1 when created, 0 when the key already existed.
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[1], 'cd', ARGV[1], 'ph', ARGV[2], 'exp', ARGV[3], 'att', '0')
redis.call('EXPIRE', KEYS[1], ARGV[4])
return 1
