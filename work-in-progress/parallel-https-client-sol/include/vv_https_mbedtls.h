#ifndef VV_HTTPS_MBEDTLS_H
#define VV_HTTPS_MBEDTLS_H

#include "vv_https_client.h"

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The integration owns DNS/TCP policy. It must return a connected,
 * nonblocking POSIX socket or a negative errno and honor the deadline and
 * cancellation token. This candidate deliberately does not implement DNS. */
typedef int (*vv_https_tcp_connect_fn)(void *arg, const char *host,
                                       uint16_t port, uint64_t deadline_ms,
                                       const struct vv_https_cancel *cancel);

/* Return true only when the board has an approved entropy source and trusted
 * wall time suitable for X.509 validity checks. */
typedef bool (*vv_https_security_ready_fn)(void *arg);

struct vv_https_mbedtls_config {
  const unsigned char *ca_pem;
  size_t ca_pem_length; /* Include the terminating NUL for PEM input. */
  vv_https_tcp_connect_fn tcp_connect;
  void *tcp_arg;
  vv_https_security_ready_fn security_ready;
  void *security_arg;
  vv_https_now_ms_fn now_ms;
  void *now_arg;
};

struct vv_https_mbedtls;

struct vv_https_mbedtls *
vv_https_mbedtls_create(const struct vv_https_mbedtls_config *config);
void vv_https_mbedtls_destroy(struct vv_https_mbedtls *transport);
const struct vv_https_transport_ops *vv_https_mbedtls_ops(void);
int vv_https_mbedtls_last_error(const struct vv_https_mbedtls *transport);

#ifdef __cplusplus
}
#endif
#endif
