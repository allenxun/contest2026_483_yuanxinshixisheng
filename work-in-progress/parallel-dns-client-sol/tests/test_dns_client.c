#include "vv_dns_client.h"

#include <stdio.h>
#include <string.h>

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define CHECK(value) do { if (!(value)) { \
  printf("FAIL line=%d expression=%s\n", __LINE__, #value); return 1; \
} } while (0)

struct fake_step
{
  enum vv_dns_status status;
  uint32_t ipv4_be;
  int code;
  uint32_t duration_ms;
};

struct fake_resolver
{
  struct fake_step steps[4];
  size_t step_count;
  size_t step_index;
  uint64_t now_ms;
  uint32_t seen_timeout[4];
  bool cancelled;
};

static enum vv_dns_status fake_resolve(void *context, const char *hostname,
                                        uint32_t timeout_ms,
                                        uint32_t *ipv4_be, int *backend_code)
{
  struct fake_resolver *fake = context;
  struct fake_step *step;
  (void)hostname;
  if (fake->step_index >= fake->step_count)
    {
      return VV_DNS_SYSTEM_FAILURE;
    }

  fake->seen_timeout[fake->step_index] = timeout_ms;
  step = &fake->steps[fake->step_index++];
  fake->now_ms += step->duration_ms;
  *ipv4_be = step->ipv4_be;
  *backend_code = step->code;
  return step->status;
}

static uint64_t fake_now(void *context)
{
  return ((struct fake_resolver *)context)->now_ms;
}

static void fake_sleep(void *context, uint32_t delay_ms)
{
  ((struct fake_resolver *)context)->now_ms += delay_ms;
}

static bool fake_cancelled(void *context)
{
  return ((struct fake_resolver *)context)->cancelled;
}

static struct vv_dns_backend fake_backend(struct fake_resolver *fake)
{
  struct vv_dns_backend backend =
  {
    fake, fake_resolve, fake_now, fake_sleep, fake_cancelled
  };
  return backend;
}

static int test_success(void)
{
  struct fake_resolver fake = { .steps = {{VV_DNS_OK, 0x01020304u, 0, 10}}, .step_count = 1 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {1000, 25, 2};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_OK);
  CHECK(result.ipv4_be == 0x01020304u && result.attempts == 1);
  CHECK(fake.seen_timeout[0] == 1000);
  return 0;
}

static int test_retry_then_success(void)
{
  struct fake_resolver fake = { .steps = {
    {VV_DNS_TEMPORARY_FAILURE, 0, 11, 100},
    {VV_DNS_OK, 0x05060708u, 0, 50}}, .step_count = 2 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {1000, 25, 2};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_OK);
  CHECK(result.attempts == 2 && result.backend_code == 0);
  CHECK(fake.seen_timeout[1] == 875);
  return 0;
}

static int test_permanent_failure_not_retried(void)
{
  struct fake_resolver fake = { .steps = {{VV_DNS_NOT_FOUND, 0, 22, 3}}, .step_count = 1 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {1000, 25, 3};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("missing.example", &policy, &backend, &result) == VV_DNS_NOT_FOUND);
  CHECK(result.attempts == 1 && result.backend_code == 22);
  return 0;
}

static int test_temporary_failure_stops_at_attempt_limit(void)
{
  struct fake_resolver fake = { .steps = {
    {VV_DNS_TEMPORARY_FAILURE, 0, 31, 1},
    {VV_DNS_TEMPORARY_FAILURE, 0, 32, 1},
    {VV_DNS_TEMPORARY_FAILURE, 0, 33, 1}}, .step_count = 3 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {1000, 1, 3};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_TEMPORARY_FAILURE);
  CHECK(result.attempts == 3 && result.backend_code == 33 && fake.step_index == 3);
  return 0;
}

static int test_deadline_after_backend(void)
{
  struct fake_resolver fake = { .steps = {{VV_DNS_OK, 1, 0, 1000}}, .step_count = 1 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {1000, 0, 1};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_DEADLINE_EXCEEDED);
  CHECK(result.ipv4_be == 0 && result.attempts == 1);
  return 0;
}

static int test_deadline_during_backoff(void)
{
  struct fake_resolver fake = { .steps = {{VV_DNS_TEMPORARY_FAILURE, 0, 1, 90}}, .step_count = 1 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {100, 25, 2};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_DEADLINE_EXCEEDED);
  CHECK(fake.now_ms == 100 && result.attempts == 1);
  return 0;
}

static int test_cancel(void)
{
  struct fake_resolver fake = {.cancelled = true};
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {100, 0, 1};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_CANCELLED);
  CHECK(result.attempts == 0);
  return 0;
}

static int test_no_ipv4(void)
{
  struct fake_resolver fake = { .steps = {{VV_DNS_OK, 0, 0, 1}}, .step_count = 1 };
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {100, 0, 1};
  struct vv_dns_result result;
  CHECK(vv_dns_resolve_ipv4("api.example.com", &policy, &backend, &result) == VV_DNS_NO_IPV4_ADDRESS);
  return 0;
}

static int test_invalid_inputs(void)
{
  struct fake_resolver fake = {0};
  struct vv_dns_backend backend = fake_backend(&fake);
  struct vv_dns_policy policy = {100, 0, 1};
  struct vv_dns_result result;
  const char *invalid[] = {"", ".bad", "bad.", "-bad.example", "bad-.example", "bad host"};
  size_t i;
  for (i = 0; i < ARRAY_SIZE(invalid); ++i)
    {
      CHECK(vv_dns_resolve_ipv4(invalid[i], &policy, &backend, &result) == VV_DNS_INVALID_ARGUMENT);
    }
  policy.max_attempts = VV_DNS_ATTEMPTS_MAX + 1u;
  CHECK(vv_dns_resolve_ipv4("api.example", &policy, &backend, &result) == VV_DNS_INVALID_ARGUMENT);
  return 0;
}

int main(void)
{
  int (*tests[])(void) = {
    test_success, test_retry_then_success, test_permanent_failure_not_retried,
    test_temporary_failure_stops_at_attempt_limit,
    test_deadline_after_backend, test_deadline_during_backoff, test_cancel,
    test_no_ipv4, test_invalid_inputs
  };
  size_t i;
  for (i = 0; i < ARRAY_SIZE(tests); ++i)
    {
      if (tests[i]() != 0)
        {
          return 1;
        }
    }

  printf("PASS dns_client_tests=%zu\n", ARRAY_SIZE(tests));
  return 0;
}
