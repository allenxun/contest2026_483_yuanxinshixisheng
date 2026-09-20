#include "vv_lease_dns.h"

#include <string.h>

static bool vv_generation_next(uint64_t current, uint64_t *next)
{
  if (next == NULL || current == UINT64_MAX) {
    return false;
  }
  *next = current + 1u;
  return *next != 0u;
}

static bool vv_ifname_copy(char out[VV_LEASE_IFNAME_CAPACITY],
                           const char *ifname)
{
  size_t length = 0u;
  if (out == NULL || ifname == NULL) {
    return false;
  }
  while (length < VV_LEASE_IFNAME_CAPACITY && ifname[length] != '\0') {
    ++length;
  }
  if (length == 0u || length >= VV_LEASE_IFNAME_CAPACITY) {
    return false;
  }
  memset(out, 0, VV_LEASE_IFNAME_CAPACITY);
  memcpy(out, ifname, length);
  return true;
}

static bool vv_unicast_ipv4(uint32_t address_be)
{
  const uint8_t first = (uint8_t)(address_be >> 24);
  return address_be != 0u && address_be != UINT32_MAX && first != 0u &&
         first < 224u && first != 127u;
}

static uint32_t vv_read_be32(const uint8_t *bytes)
{
  return ((uint32_t)bytes[0] << 24) | ((uint32_t)bytes[1] << 16) |
         ((uint32_t)bytes[2] << 8) | (uint32_t)bytes[3];
}

void vv_lease_store_init(struct vv_lease_store *store)
{
  if (store != NULL) {
    memset(store, 0, sizeof(*store));
  }
}

enum vv_lease_status vv_lease_publish_acquired(
    struct vv_lease_store *store, const char *ifname, uint32_t ipv4_be,
    uint32_t gateway_be, const uint8_t *option6, size_t option6_length)
{
  struct vv_network_snapshot next_snapshot;
  uint64_t generation;
  size_t dns_count;
  size_t index;

  if (store == NULL || ifname == NULL ||
      (option6_length != 0u && option6 == NULL)) {
    return VV_LEASE_INVALID_ARGUMENT;
  }
  if (option6_length % 4u != 0u) {
    return VV_LEASE_INVALID_OPTION6;
  }
  dns_count = option6_length / 4u;
  if (dns_count > VV_LEASE_DNS_CAPACITY) {
    return VV_LEASE_TOO_MANY_DNS;
  }
  if (!vv_unicast_ipv4(ipv4_be) || !vv_unicast_ipv4(gateway_be)) {
    return VV_LEASE_INVALID_ADDRESS;
  }
  if (!vv_generation_next(store->current.generation, &generation)) {
    return VV_LEASE_GENERATION_EXHAUSTED;
  }

  memset(&next_snapshot, 0, sizeof(next_snapshot));
  if (!vv_ifname_copy(next_snapshot.ifname, ifname)) {
    return VV_LEASE_INVALID_ARGUMENT;
  }
  for (index = 0u; index < dns_count; ++index) {
    uint32_t dns = vv_read_be32(option6 + index * 4u);
    if (!vv_unicast_ipv4(dns)) {
      return VV_LEASE_INVALID_ADDRESS;
    }
    next_snapshot.dns_ipv4_be[index] = dns;
  }

  next_snapshot.generation = generation;
  next_snapshot.link_up = true;
  next_snapshot.dhcp_ready = true;
  next_snapshot.ipv4_be = ipv4_be;
  next_snapshot.gateway_be = gateway_be;
  next_snapshot.dns_count = (uint8_t)dns_count;
  store->current = next_snapshot;
  return VV_LEASE_OK;
}

enum vv_lease_status vv_lease_publish_disconnected(
    struct vv_lease_store *store)
{
  struct vv_network_snapshot next_snapshot;
  uint64_t generation;
  if (store == NULL) {
    return VV_LEASE_INVALID_ARGUMENT;
  }
  if (!vv_generation_next(store->current.generation, &generation)) {
    return VV_LEASE_GENERATION_EXHAUSTED;
  }
  memset(&next_snapshot, 0, sizeof(next_snapshot));
  next_snapshot.generation = generation;
  store->current = next_snapshot;
  return VV_LEASE_OK;
}

void vv_lease_snapshot_copy(const struct vv_lease_store *store,
                            struct vv_network_snapshot *out)
{
  if (store != NULL && out != NULL) {
    *out = store->current;
  }
}

bool vv_lease_online(const struct vv_network_snapshot *snapshot)
{
  return snapshot != NULL && snapshot->generation != 0u && snapshot->link_up &&
         snapshot->dhcp_ready && snapshot->ifname[0] != '\0' &&
         vv_unicast_ipv4(snapshot->ipv4_be) &&
         vv_unicast_ipv4(snapshot->gateway_be);
}

bool vv_lease_dns_ready(const struct vv_network_snapshot *snapshot)
{
  size_t index;
  if (!vv_lease_online(snapshot) || snapshot->dns_count == 0u ||
      snapshot->dns_count > VV_LEASE_DNS_CAPACITY) {
    return false;
  }
  for (index = 0u; index < snapshot->dns_count; ++index) {
    if (!vv_unicast_ipv4(snapshot->dns_ipv4_be[index])) {
      return false;
    }
  }
  return true;
}

void vv_lease_cancel_token_init(struct vv_lease_cancel_token *token,
                                const struct vv_lease_store *store,
                                uint64_t generation)
{
  if (token != NULL) {
    token->store = store;
    token->generation = generation;
    token->explicit_cancel = false;
  }
}

void vv_lease_cancel_token_cancel(struct vv_lease_cancel_token *token)
{
  if (token != NULL) {
    token->explicit_cancel = true;
  }
}

bool vv_lease_cancelled(const struct vv_lease_cancel_token *token)
{
  if (token == NULL || token->store == NULL || token->explicit_cancel) {
    return true;
  }
  return token->generation == 0u ||
         token->store->current.generation != token->generation ||
         !vv_lease_online(&token->store->current);
}

void vv_cloud_supervisor_init(struct vv_cloud_supervisor *supervisor,
                              const struct vv_lease_store *store)
{
  if (supervisor != NULL) {
    supervisor->state = VV_CLOUD_OFFLINE;
    supervisor->generation = 0u;
    supervisor->store = store;
  }
}

void vv_cloud_supervisor_observe(struct vv_cloud_supervisor *supervisor)
{
  const struct vv_network_snapshot *snapshot;
  if (supervisor == NULL) {
    return;
  }
  snapshot = supervisor->store == NULL ? NULL : &supervisor->store->current;
  if (!vv_lease_online(snapshot)) {
    supervisor->state = VV_CLOUD_OFFLINE;
    supervisor->generation = snapshot == NULL ? 0u : snapshot->generation;
    return;
  }
  if (supervisor->generation != snapshot->generation ||
      supervisor->state == VV_CLOUD_OFFLINE) {
    supervisor->generation = snapshot->generation;
    supervisor->state = VV_CLOUD_LEASE_READY;
  }
}

static enum vv_lease_status vv_cloud_generation(
    const struct vv_cloud_supervisor *supervisor, uint64_t generation)
{
  if (supervisor == NULL || generation == 0u) {
    return VV_LEASE_INVALID_ARGUMENT;
  }
  if (supervisor->store == NULL || supervisor->generation != generation ||
      supervisor->store->current.generation != generation ||
      !vv_lease_online(&supervisor->store->current)) {
    return VV_LEASE_STALE;
  }
  return VV_LEASE_OK;
}

enum vv_lease_status vv_cloud_begin_dns(
    struct vv_cloud_supervisor *supervisor)
{
  const struct vv_network_snapshot *snapshot;
  if (supervisor == NULL || supervisor->store == NULL) {
    return VV_LEASE_INVALID_ARGUMENT;
  }
  snapshot = &supervisor->store->current;
  if (supervisor->generation != snapshot->generation) {
    return VV_LEASE_STALE;
  }
  if (supervisor->state != VV_CLOUD_LEASE_READY) {
    return VV_LEASE_WRONG_STATE;
  }
  if (!vv_lease_dns_ready(snapshot)) {
    return VV_LEASE_NO_DNS;
  }
  supervisor->state = VV_CLOUD_DNS_PROBING;
  return VV_LEASE_OK;
}

enum vv_lease_status vv_cloud_mark_dns_ready(
    struct vv_cloud_supervisor *supervisor, uint64_t generation)
{
  enum vv_lease_status status = vv_cloud_generation(supervisor, generation);
  if (status != VV_LEASE_OK) {
    return status;
  }
  if (supervisor->state != VV_CLOUD_DNS_PROBING) {
    return VV_LEASE_WRONG_STATE;
  }
  supervisor->state = VV_CLOUD_DNS_READY;
  return VV_LEASE_OK;
}

enum vv_lease_status vv_cloud_mark_trust_ready(
    struct vv_cloud_supervisor *supervisor, uint64_t generation)
{
  enum vv_lease_status status = vv_cloud_generation(supervisor, generation);
  if (status != VV_LEASE_OK) {
    return status;
  }
  if (supervisor->state != VV_CLOUD_DNS_READY) {
    return VV_LEASE_WRONG_STATE;
  }
  supervisor->state = VV_CLOUD_TRUST_READY;
  return VV_LEASE_OK;
}

enum vv_lease_status vv_cloud_begin_tls(
    struct vv_cloud_supervisor *supervisor, uint64_t generation)
{
  enum vv_lease_status status = vv_cloud_generation(supervisor, generation);
  if (status != VV_LEASE_OK) {
    return status;
  }
  if (supervisor->state != VV_CLOUD_TRUST_READY) {
    return VV_LEASE_WRONG_STATE;
  }
  supervisor->state = VV_CLOUD_TLS_PROBING;
  return VV_LEASE_OK;
}

enum vv_lease_status vv_cloud_mark_tls_ready(
    struct vv_cloud_supervisor *supervisor, uint64_t generation)
{
  enum vv_lease_status status = vv_cloud_generation(supervisor, generation);
  if (status != VV_LEASE_OK) {
    return status;
  }
  if (supervisor->state != VV_CLOUD_TLS_PROBING) {
    return VV_LEASE_WRONG_STATE;
  }
  supervisor->state = VV_CLOUD_READY;
  return VV_LEASE_OK;
}

bool vv_cloud_can_start_request(
    const struct vv_cloud_supervisor *supervisor)
{
  const struct vv_network_snapshot *snapshot =
      supervisor == NULL || supervisor->store == NULL
          ? NULL
          : &supervisor->store->current;
  return supervisor != NULL && vv_lease_dns_ready(snapshot) &&
         supervisor->state == VV_CLOUD_READY &&
         supervisor->generation == snapshot->generation;
}

const char *vv_cloud_state_name(enum vv_cloud_state state)
{
  switch (state) {
    case VV_CLOUD_OFFLINE: return "OFFLINE";
    case VV_CLOUD_LEASE_READY: return "LEASE_READY";
    case VV_CLOUD_DNS_PROBING: return "DNS_PROBING";
    case VV_CLOUD_DNS_READY: return "DNS_READY";
    case VV_CLOUD_TRUST_READY: return "TRUST_READY";
    case VV_CLOUD_TLS_PROBING: return "TLS_PROBING";
    case VV_CLOUD_READY: return "CLOUD_READY";
    default: return "UNKNOWN";
  }
}
