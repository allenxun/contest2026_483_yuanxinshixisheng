#include "vv_https_mbedtls.h"

#include <errno.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>

#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/ssl.h>
#include <mbedtls/x509_crt.h>

struct vv_https_mbedtls {
  struct vv_https_mbedtls_config cfg;
  mbedtls_net_context net;
  mbedtls_ssl_context ssl;
  mbedtls_ssl_config ssl_cfg;
  mbedtls_x509_crt ca;
  mbedtls_entropy_context entropy;
  mbedtls_ctr_drbg_context drbg;
  int last_error;
  bool initialized;
};

static bool is_cancelled(const struct vv_https_cancel *c) {
  return c && c->is_cancelled && c->is_cancelled(c->arg);
}

static int wait_fd(struct vv_https_mbedtls *t, short events,
                   uint64_t deadline, const struct vv_https_cancel *cancel) {
  for (;;) {
    if (is_cancelled(cancel)) return -ECANCELED;
    uint64_t now = t->cfg.now_ms(t->cfg.now_arg);
    if (now >= deadline) return -ETIMEDOUT;
    uint64_t remain = deadline - now;
    int slice = remain > 50 ? 50 : (int)remain;
    struct pollfd pfd = {.fd = t->net.fd, .events = events};
    int rc = poll(&pfd, 1, slice);
    if (rc > 0) {
      if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) return -EIO;
      if (pfd.revents & events) return 0;
    } else if (rc < 0 && errno != EINTR) {
      return -errno;
    }
  }
}

static int wait_mbed(struct vv_https_mbedtls *t, int rc, uint64_t deadline,
                     const struct vv_https_cancel *cancel) {
  if (rc == MBEDTLS_ERR_SSL_WANT_READ)
    return wait_fd(t, POLLIN, deadline, cancel);
  if (rc == MBEDTLS_ERR_SSL_WANT_WRITE)
    return wait_fd(t, POLLOUT, deadline, cancel);
  return rc;
}

static void reset_connection(struct vv_https_mbedtls *t) {
  if (t->net.fd >= 0) mbedtls_net_free(&t->net);
  mbedtls_ssl_free(&t->ssl);
  mbedtls_ssl_init(&t->ssl);
}

static int tls_connect(void *ctx, const char *host, uint16_t port,
                       uint64_t deadline,
                       const struct vv_https_cancel *cancel,
                       struct vv_https_peer_security *security) {
  struct vv_https_mbedtls *t = ctx;
  int rc;
  memset(security, 0, sizeof(*security));
  reset_connection(t);
  if (!t->cfg.security_ready(t->cfg.security_arg))
    return VV_HTTPS_ETLS_VERIFY;
  rc = t->cfg.tcp_connect(t->cfg.tcp_arg, host, port, deadline, cancel);
  if (rc < 0) return rc;
  t->net.fd = rc;
  rc = mbedtls_ssl_setup(&t->ssl, &t->ssl_cfg);
  if (rc) goto fail;
  rc = mbedtls_ssl_set_hostname(&t->ssl, host);
  if (rc) goto fail;
  security->sni_set = true;
  mbedtls_ssl_set_bio(&t->ssl, &t->net, mbedtls_net_send,
                      mbedtls_net_recv, NULL);
  for (;;) {
    if (is_cancelled(cancel)) { rc = -ECANCELED; goto fail; }
    if (t->cfg.now_ms(t->cfg.now_arg) >= deadline)
      { rc = -ETIMEDOUT; goto fail; }
    rc = mbedtls_ssl_handshake(&t->ssl);
    if (!rc) break;
    int waited = wait_mbed(t, rc, deadline, cancel);
    if (waited < 0 && waited != MBEDTLS_ERR_SSL_WANT_READ &&
        waited != MBEDTLS_ERR_SSL_WANT_WRITE) {
      rc = waited;
      goto fail;
    }
  }
  security->verify_flags = mbedtls_ssl_get_verify_result(&t->ssl);
  security->peer_verified = security->verify_flags == 0 &&
                            mbedtls_ssl_get_peer_cert(&t->ssl) != NULL;
  if (!security->peer_verified) { rc = VV_HTTPS_ETLS_VERIFY; goto fail; }
  t->last_error = 0;
  return 0;
fail:
  t->last_error = rc;
  reset_connection(t);
  return rc;
}

static ssize_t tls_write(void *ctx, const void *data, size_t len,
                         uint64_t deadline,
                         const struct vv_https_cancel *cancel) {
  struct vv_https_mbedtls *t = ctx;
  for (;;) {
    if (is_cancelled(cancel)) return -ECANCELED;
    if (t->cfg.now_ms(t->cfg.now_arg) >= deadline) return -ETIMEDOUT;
    int rc = mbedtls_ssl_write(&t->ssl, data, len);
    if (rc >= 0) return rc;
    int waited = wait_mbed(t, rc, deadline, cancel);
    if (waited < 0 && waited != MBEDTLS_ERR_SSL_WANT_READ &&
        waited != MBEDTLS_ERR_SSL_WANT_WRITE) {
      t->last_error = rc;
      return waited == rc ? -EIO : waited;
    }
  }
}

static ssize_t tls_read(void *ctx, void *data, size_t len,
                        uint64_t deadline,
                        const struct vv_https_cancel *cancel) {
  struct vv_https_mbedtls *t = ctx;
  for (;;) {
    if (is_cancelled(cancel)) return -ECANCELED;
    if (t->cfg.now_ms(t->cfg.now_arg) >= deadline) return -ETIMEDOUT;
    int rc = mbedtls_ssl_read(&t->ssl, data, len);
    if (rc >= 0) return rc;
    if (rc == MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY) return 0;
    int waited = wait_mbed(t, rc, deadline, cancel);
    if (waited < 0 && waited != MBEDTLS_ERR_SSL_WANT_READ &&
        waited != MBEDTLS_ERR_SSL_WANT_WRITE) {
      t->last_error = rc;
      return waited == rc ? -EIO : waited;
    }
  }
}

static void tls_close(void *ctx) {
  struct vv_https_mbedtls *t = ctx;
  if (t->net.fd >= 0) (void)mbedtls_ssl_close_notify(&t->ssl);
  reset_connection(t);
}

static const struct vv_https_transport_ops g_ops = {
  .connect = tls_connect, .write = tls_write, .read = tls_read,
  .close = tls_close
};

struct vv_https_mbedtls *
vv_https_mbedtls_create(const struct vv_https_mbedtls_config *cfg) {
  static const unsigned char personalization[] = "velavision-https-client";
  if (!cfg || !cfg->ca_pem || !cfg->ca_pem_length || !cfg->tcp_connect ||
      !cfg->security_ready || !cfg->now_ms) return NULL;
  /* Do not even seed the DRBG until platform trust prerequisites pass. */
  if (!cfg->security_ready(cfg->security_arg)) return NULL;
  struct vv_https_mbedtls *t = calloc(1, sizeof(*t));
  if (!t) return NULL;
  t->cfg = *cfg;
  mbedtls_net_init(&t->net);
  mbedtls_ssl_init(&t->ssl);
  mbedtls_ssl_config_init(&t->ssl_cfg);
  mbedtls_x509_crt_init(&t->ca);
  mbedtls_entropy_init(&t->entropy);
  mbedtls_ctr_drbg_init(&t->drbg);
  int rc = mbedtls_ctr_drbg_seed(&t->drbg, mbedtls_entropy_func, &t->entropy,
                                 personalization,
                                 sizeof(personalization) - 1);
  if (!rc) rc = mbedtls_x509_crt_parse(&t->ca, cfg->ca_pem,
                                        cfg->ca_pem_length);
  if (!rc) rc = mbedtls_ssl_config_defaults(&t->ssl_cfg,
      MBEDTLS_SSL_IS_CLIENT, MBEDTLS_SSL_TRANSPORT_STREAM,
      MBEDTLS_SSL_PRESET_DEFAULT);
  if (rc) { t->last_error = rc; vv_https_mbedtls_destroy(t); return NULL; }
  mbedtls_ssl_conf_authmode(&t->ssl_cfg, MBEDTLS_SSL_VERIFY_REQUIRED);
  mbedtls_ssl_conf_ca_chain(&t->ssl_cfg, &t->ca, NULL);
  mbedtls_ssl_conf_rng(&t->ssl_cfg, mbedtls_ctr_drbg_random, &t->drbg);
  t->initialized = true;
  return t;
}

void vv_https_mbedtls_destroy(struct vv_https_mbedtls *t) {
  if (!t) return;
  reset_connection(t);
  mbedtls_ssl_config_free(&t->ssl_cfg);
  mbedtls_x509_crt_free(&t->ca);
  mbedtls_ctr_drbg_free(&t->drbg);
  mbedtls_entropy_free(&t->entropy);
  vv_https_secure_zero(t, sizeof(*t));
  free(t);
}

const struct vv_https_transport_ops *vv_https_mbedtls_ops(void) {
  return &g_ops;
}

int vv_https_mbedtls_last_error(const struct vv_https_mbedtls *t) {
  return t ? t->last_error : 0;
}
