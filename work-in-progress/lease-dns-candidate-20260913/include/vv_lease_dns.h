#ifndef VV_LEASE_DNS_H
#define VV_LEASE_DNS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VV_LEASE_IFNAME_CAPACITY 16u
#define VV_LEASE_DNS_CAPACITY 2u

enum vv_lease_status {
  VV_LEASE_OK = 0,
  VV_LEASE_INVALID_ARGUMENT = -1,
  VV_LEASE_INVALID_ADDRESS = -2,
  VV_LEASE_INVALID_OPTION6 = -3,
  VV_LEASE_TOO_MANY_DNS = -4,
  VV_LEASE_GENERATION_EXHAUSTED = -5,
  VV_LEASE_STALE = -6,
  VV_LEASE_NO_DNS = -7,
  VV_LEASE_WRONG_STATE = -8
};

struct vv_network_snapshot {
  uint64_t generation;
  bool link_up;
  bool dhcp_ready;
  char ifname[VV_LEASE_IFNAME_CAPACITY];
  uint32_t ipv4_be;
  uint32_t gateway_be;
  uint32_t dns_ipv4_be[VV_LEASE_DNS_CAPACITY];
  uint8_t dns_count;
};

/* The owner must serialize all access with the radio IP-state lock. The store
 * owns every byte; snapshots never borrow DHCP or credential storage. */
struct vv_lease_store {
  struct vv_network_snapshot current;
};

struct vv_lease_cancel_token {
  const struct vv_lease_store *store;
  uint64_t generation;
  bool explicit_cancel;
};

enum vv_cloud_state {
  VV_CLOUD_OFFLINE = 0,
  VV_CLOUD_LEASE_READY,
  VV_CLOUD_DNS_PROBING,
  VV_CLOUD_DNS_READY,
  VV_CLOUD_TRUST_READY,
  VV_CLOUD_TLS_PROBING,
  VV_CLOUD_READY
};

struct vv_cloud_supervisor {
  enum vv_cloud_state state;
  uint64_t generation;
  const struct vv_lease_store *store;
};

void vv_lease_store_init(struct vv_lease_store *store);

/* option6 is the DHCP option-6 payload only: zero, one, or two IPv4 addresses.
 * An absent option is published as dns_count=0 so Wi-Fi success remains true,
 * while the cloud DNS gate fails closed. */
enum vv_lease_status vv_lease_publish_acquired(
    struct vv_lease_store *store, const char *ifname, uint32_t ipv4_be,
    uint32_t gateway_be, const uint8_t *option6, size_t option6_length);

enum vv_lease_status vv_lease_publish_disconnected(
    struct vv_lease_store *store);

void vv_lease_snapshot_copy(const struct vv_lease_store *store,
                            struct vv_network_snapshot *out);

bool vv_lease_online(const struct vv_network_snapshot *snapshot);
bool vv_lease_dns_ready(const struct vv_network_snapshot *snapshot);

void vv_lease_cancel_token_init(struct vv_lease_cancel_token *token,
                                const struct vv_lease_store *store,
                                uint64_t generation);
void vv_lease_cancel_token_cancel(struct vv_lease_cancel_token *token);
bool vv_lease_cancelled(const struct vv_lease_cancel_token *token);

void vv_cloud_supervisor_init(struct vv_cloud_supervisor *supervisor,
                              const struct vv_lease_store *store);
void vv_cloud_supervisor_observe(struct vv_cloud_supervisor *supervisor);
enum vv_lease_status vv_cloud_begin_dns(
    struct vv_cloud_supervisor *supervisor);
enum vv_lease_status vv_cloud_mark_dns_ready(
    struct vv_cloud_supervisor *supervisor, uint64_t generation);
enum vv_lease_status vv_cloud_mark_trust_ready(
    struct vv_cloud_supervisor *supervisor, uint64_t generation);
enum vv_lease_status vv_cloud_begin_tls(
    struct vv_cloud_supervisor *supervisor, uint64_t generation);
enum vv_lease_status vv_cloud_mark_tls_ready(
    struct vv_cloud_supervisor *supervisor, uint64_t generation);
bool vv_cloud_can_start_request(
    const struct vv_cloud_supervisor *supervisor);

const char *vv_cloud_state_name(enum vv_cloud_state state);

#ifdef __cplusplus
}
#endif

#endif
