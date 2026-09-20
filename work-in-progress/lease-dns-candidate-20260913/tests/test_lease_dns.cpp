#include "vv_lease_dns.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <type_traits>

namespace {

unsigned tests_run = 0;

#define CHECK(expr)                                                           \
  do {                                                                        \
    ++tests_run;                                                              \
    if (!(expr)) {                                                            \
      std::fprintf(stderr, "FAIL line=%d expression=%s\n", __LINE__, #expr); \
      return false;                                                           \
    }                                                                         \
  } while (false)

constexpr std::uint32_t ip(unsigned a, unsigned b, unsigned c, unsigned d) {
  return (a << 24) | (b << 16) | (c << 8) | d;
}

bool driveCloudReady(vv_cloud_supervisor &supervisor,
                     const vv_network_snapshot &snapshot) {
  CHECK(vv_cloud_begin_dns(&supervisor) == VV_LEASE_OK);
  CHECK(vv_cloud_mark_dns_ready(&supervisor, snapshot.generation) ==
        VV_LEASE_OK);
  CHECK(vv_cloud_mark_trust_ready(&supervisor, snapshot.generation) ==
        VV_LEASE_OK);
  CHECK(vv_cloud_begin_tls(&supervisor, snapshot.generation) == VV_LEASE_OK);
  CHECK(vv_cloud_mark_tls_ready(&supervisor, snapshot.generation) ==
        VV_LEASE_OK);
  return true;
}

bool testPublishAndCloudGate() {
  const std::uint8_t option6[] = {1, 1, 1, 1, 8, 8, 8, 8};
  vv_lease_store store{};
  vv_network_snapshot snapshot{};
  vv_cloud_supervisor supervisor{};
  vv_lease_cancel_token token{};

  vv_lease_store_init(&store);
  vv_cloud_supervisor_init(&supervisor, &store);
  CHECK(store.current.generation == 0);
  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 3, 0, 214),
                                  ip(10, 3, 0, 1), option6,
                                  sizeof(option6)) == VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &snapshot);
  CHECK(snapshot.generation == 1);
  CHECK(snapshot.link_up && snapshot.dhcp_ready);
  CHECK(std::strcmp(snapshot.ifname, "wlan0") == 0);
  CHECK(snapshot.ipv4_be == ip(10, 3, 0, 214));
  CHECK(snapshot.gateway_be == ip(10, 3, 0, 1));
  CHECK(snapshot.dns_count == 2);
  CHECK(snapshot.dns_ipv4_be[0] == ip(1, 1, 1, 1));
  CHECK(snapshot.dns_ipv4_be[1] == ip(8, 8, 8, 8));
  CHECK(vv_lease_online(&snapshot));
  CHECK(vv_lease_dns_ready(&snapshot));

  vv_lease_cancel_token_init(&token, &store, snapshot.generation);
  CHECK(!vv_lease_cancelled(&token));
  vv_cloud_supervisor_observe(&supervisor);
  CHECK(supervisor.state == VV_CLOUD_LEASE_READY);
  CHECK(!vv_cloud_can_start_request(&supervisor));
  CHECK(vv_cloud_mark_dns_ready(&supervisor, snapshot.generation) ==
        VV_LEASE_WRONG_STATE);
  CHECK(driveCloudReady(supervisor, snapshot));
  CHECK(vv_cloud_can_start_request(&supervisor));
  CHECK(!vv_lease_cancelled(&token));
  return true;
}

bool testNoDnsFailsClosed() {
  vv_lease_store store{};
  vv_network_snapshot snapshot{};
  vv_cloud_supervisor supervisor{};
  vv_lease_store_init(&store);
  vv_cloud_supervisor_init(&supervisor, &store);

  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 3, 0, 214),
                                  ip(10, 3, 0, 1), nullptr, 0) ==
        VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &snapshot);
  CHECK(vv_lease_online(&snapshot));
  CHECK(!vv_lease_dns_ready(&snapshot));
  vv_cloud_supervisor_observe(&supervisor);
  CHECK(supervisor.state == VV_CLOUD_LEASE_READY);
  CHECK(vv_cloud_begin_dns(&supervisor) == VV_LEASE_NO_DNS);
  CHECK(supervisor.state == VV_CLOUD_LEASE_READY);
  CHECK(!vv_cloud_can_start_request(&supervisor));
  return true;
}

bool testDisconnectCancelsImmediately() {
  const std::uint8_t option6[] = {9, 9, 9, 9};
  vv_lease_store store{};
  vv_network_snapshot before{};
  vv_network_snapshot after{};
  vv_lease_cancel_token token{};
  vv_cloud_supervisor supervisor{};
  vv_lease_store_init(&store);
  vv_cloud_supervisor_init(&supervisor, &store);

  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 3, 0, 214),
                                  ip(10, 3, 0, 1), option6,
                                  sizeof(option6)) == VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &before);
  vv_lease_cancel_token_init(&token, &store, before.generation);
  vv_cloud_supervisor_observe(&supervisor);
  CHECK(driveCloudReady(supervisor, before));

  CHECK(vv_lease_publish_disconnected(&store) == VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &after);
  CHECK(after.generation == before.generation + 1);
  CHECK(!after.link_up && !after.dhcp_ready);
  CHECK(after.ifname[0] == '\0');
  CHECK(after.ipv4_be == 0 && after.gateway_be == 0);
  CHECK(after.dns_count == 0 && after.dns_ipv4_be[0] == 0);
  CHECK(vv_lease_cancelled(&token));
  CHECK(!vv_cloud_can_start_request(&supervisor));
  CHECK(vv_cloud_mark_tls_ready(&supervisor, before.generation) ==
        VV_LEASE_STALE);
  vv_cloud_supervisor_observe(&supervisor);
  CHECK(supervisor.state == VV_CLOUD_OFFLINE);
  return true;
}

bool testReconnectRequiresNewGenerationGates() {
  const std::uint8_t first_dns[] = {1, 1, 1, 1};
  const std::uint8_t second_dns[] = {8, 8, 4, 4};
  vv_lease_store store{};
  vv_network_snapshot first{};
  vv_network_snapshot offline{};
  vv_network_snapshot second{};
  vv_lease_cancel_token first_token{};
  vv_lease_cancel_token second_token{};
  vv_cloud_supervisor supervisor{};
  vv_lease_store_init(&store);
  vv_cloud_supervisor_init(&supervisor, &store);

  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 3, 0, 20),
                                  ip(10, 3, 0, 1), first_dns,
                                  sizeof(first_dns)) == VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &first);
  vv_lease_cancel_token_init(&first_token, &store, first.generation);
  vv_cloud_supervisor_observe(&supervisor);
  CHECK(driveCloudReady(supervisor, first));
  CHECK(vv_cloud_can_start_request(&supervisor));

  CHECK(vv_lease_publish_disconnected(&store) == VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &offline);
  vv_cloud_supervisor_observe(&supervisor);
  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 3, 0, 21),
                                  ip(10, 3, 0, 1), second_dns,
                                  sizeof(second_dns)) == VV_LEASE_OK);
  vv_lease_snapshot_copy(&store, &second);
  CHECK(second.generation == first.generation + 2);
  CHECK(second.dns_ipv4_be[0] == ip(8, 8, 4, 4));
  CHECK(vv_lease_cancelled(&first_token));
  CHECK(vv_cloud_begin_dns(&supervisor) == VV_LEASE_STALE);

  vv_cloud_supervisor_observe(&supervisor);
  CHECK(supervisor.generation == second.generation);
  CHECK(supervisor.state == VV_CLOUD_LEASE_READY);
  CHECK(!vv_cloud_can_start_request(&supervisor));
  CHECK(vv_cloud_mark_dns_ready(&supervisor, first.generation) ==
        VV_LEASE_STALE);
  vv_lease_cancel_token_init(&second_token, &store, second.generation);
  CHECK(!vv_lease_cancelled(&second_token));
  CHECK(driveCloudReady(supervisor, second));
  CHECK(vv_cloud_can_start_request(&supervisor));
  return true;
}

bool testValidationAndExplicitCancel() {
  const std::uint8_t malformed[] = {1, 1, 1};
  const std::uint8_t too_many[] = {1, 1, 1, 1, 8, 8, 8, 8, 9, 9, 9, 9};
  const std::uint8_t multicast[] = {224, 0, 0, 1};
  const std::uint8_t valid[] = {1, 0, 0, 1};
  vv_lease_store store{};
  vv_lease_cancel_token token{};
  vv_lease_store_init(&store);

  CHECK(vv_lease_publish_acquired(&store, "", ip(10, 0, 0, 2),
                                  ip(10, 0, 0, 1), valid, sizeof(valid)) ==
        VV_LEASE_INVALID_ARGUMENT);
  CHECK(vv_lease_publish_acquired(&store, "wlan0", 0, ip(10, 0, 0, 1),
                                  valid, sizeof(valid)) ==
        VV_LEASE_INVALID_ADDRESS);
  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 0, 0, 2),
                                  ip(10, 0, 0, 1), malformed,
                                  sizeof(malformed)) ==
        VV_LEASE_INVALID_OPTION6);
  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 0, 0, 2),
                                  ip(10, 0, 0, 1), too_many,
                                  sizeof(too_many)) == VV_LEASE_TOO_MANY_DNS);
  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 0, 0, 2),
                                  ip(10, 0, 0, 1), multicast,
                                  sizeof(multicast)) ==
        VV_LEASE_INVALID_ADDRESS);
  CHECK(store.current.generation == 0);

  CHECK(vv_lease_publish_acquired(&store, "wlan0", ip(10, 0, 0, 2),
                                  ip(10, 0, 0, 1), valid, sizeof(valid)) ==
        VV_LEASE_OK);
  vv_lease_cancel_token_init(&token, &store, store.current.generation);
  CHECK(!vv_lease_cancelled(&token));
  vv_lease_cancel_token_cancel(&token);
  CHECK(vv_lease_cancelled(&token));

  store.current.generation = UINT64_MAX;
  CHECK(vv_lease_publish_disconnected(&store) ==
        VV_LEASE_GENERATION_EXHAUSTED);
  CHECK(store.current.generation == UINT64_MAX);
  return true;
}

}  // namespace

int main() {
  static_assert(std::is_standard_layout<vv_network_snapshot>::value,
                "snapshot must remain a C-compatible value type");
  static_assert(sizeof(vv_network_snapshot) <= 64,
                "snapshot must remain fixed and small");

  if (!testPublishAndCloudGate() || !testNoDnsFailsClosed() ||
      !testDisconnectCancelsImmediately() ||
      !testReconnectRequiresNewGenerationGates() ||
      !testValidationAndExplicitCancel()) {
    return 1;
  }
  std::printf("PASS tests=%u cancellation_observation_ms=0 heap_bytes=0\n",
              tests_run);
  return 0;
}
