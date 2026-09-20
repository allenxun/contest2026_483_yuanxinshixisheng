#include "vv_https_client.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct fake {
  const unsigned char *response;
  size_t response_len;
  size_t response_at;
  size_t max_read;
  unsigned char written[8192];
  size_t written_len;
  int connects;
  int closes;
  int connect_error;
  struct vv_https_peer_security security;
  uint64_t now;
  uint64_t now_step;
  bool cancel;
};

static uint64_t fake_now(void *arg) {
  struct fake *f = arg;
  uint64_t n = f->now;
  f->now += f->now_step;
  return n;
}

static bool fake_cancel(void *arg) { return ((struct fake *)arg)->cancel; }

static int fake_connect(void *arg, const char *host, uint16_t port,
                        uint64_t deadline,
                        const struct vv_https_cancel *cancel,
                        struct vv_https_peer_security *security) {
  struct fake *f = arg;
  (void)host; (void)port; (void)deadline; (void)cancel;
  f->connects++;
  *security = f->security;
  return f->connect_error;
}

static ssize_t fake_write(void *arg, const void *data, size_t len,
                          uint64_t deadline,
                          const struct vv_https_cancel *cancel) {
  struct fake *f = arg;
  (void)deadline; (void)cancel;
  if (len > sizeof(f->written) - f->written_len) return -EIO;
  size_t n = len > 7 ? 7 : len;
  memcpy(f->written + f->written_len, data, n);
  f->written_len += n;
  return (ssize_t)n;
}

static ssize_t fake_read(void *arg, void *data, size_t len,
                         uint64_t deadline,
                         const struct vv_https_cancel *cancel) {
  struct fake *f = arg;
  (void)deadline; (void)cancel;
  if (f->response_at == f->response_len) return 0;
  size_t n = f->response_len - f->response_at;
  if (n > len) n = len;
  if (f->max_read && n > f->max_read) n = f->max_read;
  memcpy(data, f->response + f->response_at, n);
  f->response_at += n;
  return (ssize_t)n;
}

static void fake_close(void *arg) { ((struct fake *)arg)->closes++; }

static const struct vv_https_transport_ops fake_ops = {
  fake_connect, fake_write, fake_read, fake_close
};

struct bytes { const unsigned char *p; size_t n; };
static ssize_t body_read(void *arg, size_t offset, void *dst, size_t cap) {
  struct bytes *b = arg;
  if (offset >= b->n) return 0;
  size_t n = b->n - offset;
  if (n > cap) n = cap;
  memcpy(dst, b->p + offset, n);
  return (ssize_t)n;
}

struct sink { unsigned char p[4096]; size_t n; bool reject; };
static int sink_write(void *arg, const void *data, size_t len) {
  struct sink *s = arg;
  if (s->reject || len > sizeof(s->p) - s->n) return -1;
  memcpy(s->p + s->n, data, len); s->n += len; return 0;
}

struct logs { char text[256]; size_t n; };
static void log_event(void *arg, const char *event, int value) {
  struct logs *logs = arg;
  int n = snprintf(logs->text + logs->n, sizeof(logs->text) - logs->n,
                   "%s=%d;", event, value);
  if (n > 0 && (size_t)n < sizeof(logs->text) - logs->n) logs->n += (size_t)n;
}

static struct vv_https_client client(struct fake *f) {
  struct vv_https_client c = {
    .transport = &fake_ops, .transport_ctx = f,
    .now_ms = fake_now, .now_arg = f,
    .limits = {2048, 2048, 2048, 1024, 1000}
  };
  return c;
}

static struct vv_https_request request(void) {
  struct vv_https_request q = {.method="POST", .host="api.example.test",
                               .path="/v1/respond"};
  return q;
}

static struct fake fake_for(const char *response) {
  struct fake f = {.response=(const unsigned char *)response,
                   .response_len=strlen(response), .max_read=3,
                   .security={true,true,0}};
  return f;
}

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "%s:%d check failed: %s\n", __FILE__, __LINE__, #x); \
  return 1; } } while (0)

static int perform(struct fake *f, struct vv_https_request *q,
                   struct vv_https_client *c, struct sink *s,
                   struct vv_https_response *out) {
  struct vv_https_cancel cancel = {fake_cancel, f};
  return vv_https_perform(c, q, sink_write, s, &cancel, out);
}

static int test_content_length_and_request(void) {
  struct fake f = fake_for("HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello");
  struct vv_https_client c = client(&f); struct vv_https_request q = request();
  q.port = 18085;
  struct logs logs={0}; c.log=log_event; c.log_arg=&logs;
  const unsigned char json[] = "{\"x\":1}"; struct bytes b={json,sizeof(json)-1};
  struct vv_https_header h={"Authorization","Bearer secret-value",true};
  q.headers=&h; q.header_count=1; q.body_length=b.n; q.body_read=body_read; q.body_arg=&b;
  struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==0); CHECK(out.status_code==200);
  CHECK(s.n==5 && !memcmp(s.p,"hello",5)); CHECK(f.closes==1);
  f.written[f.written_len]=0;
  CHECK(strstr((char *)f.written,"Host: api.example.test:18085\r\n"));
  CHECK(strstr((char *)f.written,"Authorization: Bearer secret-value\r\n"));
  CHECK(strstr((char *)f.written,"Content-Length: 7\r\n"));
  CHECK(!strstr(logs.text,"secret-value"));
  return 0;
}

static int test_chunked(void) {
  struct fake f=fake_for("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n4;foo=bar\r\nWiki\r\n5\r\npedia\r\n0\r\nX-End: yes\r\n\r\n");
  struct vv_https_client c=client(&f); struct vv_https_request q=request();
  struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==0); CHECK(out.chunked && out.body_bytes==9);
  CHECK(!memcmp(s.p,"Wikipedia",9)); return 0;
}

static int expect_error(const char *response, int expected) {
  struct fake f=fake_for(response); struct vv_https_client c=client(&f);
  struct vv_https_request q=request(); struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==expected); CHECK(f.closes==1); return 0;
}

static int test_protocol_rejections(void) {
  CHECK(!expect_error("HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",VV_HTTPS_EPROTO));
  CHECK(!expect_error("HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nabc",VV_HTTPS_EPROTO));
  CHECK(!expect_error("HTTP/1.1 204 No Content\r\nContent-Length: 1\r\n\r\nx",VV_HTTPS_EPROTO));
  CHECK(!expect_error("HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip, chunked\r\n\r\n",VV_HTTPS_EPROTO));
  return 0;
}

static int test_limits(void) {
  struct fake f=fake_for("HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\n123456");
  struct vv_https_client c=client(&f); c.limits.max_response_body_bytes=5;
  struct vv_https_request q=request(); struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_ELIMIT); CHECK(f.closes==1);
  f=fake_for("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\n12345\r\n0\r\n\r\n");
  c=client(&f); c.limits.max_chunk_bytes=4;
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_ELIMIT); CHECK(f.closes==1);
  return 0;
}

static int test_tls_gate(void) {
  struct fake f=fake_for(""); f.security.peer_verified=false;
  struct vv_https_client c=client(&f); struct vv_https_request q=request();
  struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_ETLS_VERIFY);
  CHECK(f.written_len==0 && f.closes==1); return 0;
}

static int test_cancel_and_timeout(void) {
  struct fake f=fake_for(""); f.cancel=true;
  struct vv_https_client c=client(&f); struct vv_https_request q=request();
  struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_ECANCELLED);
  CHECK(f.connects==0 && f.closes==0);
  f=fake_for(""); f.now_step=1001; c=client(&f);
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_ETIMEOUT);
  CHECK(f.connects==0 && f.closes==0); return 0;
}

static int test_sink_cleanup(void) {
  struct fake f=fake_for("HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nx");
  struct vv_https_client c=client(&f); struct vv_https_request q=request();
  struct sink s={.reject=true}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_ESINK); CHECK(f.closes==1); return 0;
}

static int test_header_injection(void) {
  struct fake f=fake_for(""); struct vv_https_client c=client(&f);
  struct vv_https_request q=request();
  struct vv_https_header h={"Authorization","safe\r\nInjected: yes",true};
  q.headers=&h; q.header_count=1; struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_EINVAL); CHECK(f.connects==0);
  f=fake_for(""); c=client(&f); q=request(); q.path="/bad path";
  CHECK(perform(&f,&q,&c,&s,&out)==VV_HTTPS_EINVAL); CHECK(f.connects==0);
  return 0;
}

static int test_eof_body(void) {
  struct fake f=fake_for("HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nbye");
  struct vv_https_client c=client(&f); struct vv_https_request q=request();
  struct sink s={0}; struct vv_https_response out;
  CHECK(perform(&f,&q,&c,&s,&out)==0); CHECK(s.n==3 && !memcmp(s.p,"bye",3)); return 0;
}

int main(void) {
  int (*tests[])(void)={test_content_length_and_request,test_chunked,
    test_protocol_rejections,test_limits,test_tls_gate,test_cancel_and_timeout,
    test_sink_cleanup,test_header_injection,test_eof_body};
  const char *names[]={"content_length_and_request","chunked",
    "protocol_rejections","limits","tls_gate","cancel_and_timeout",
    "sink_cleanup","header_injection","eof_body"};
  for (size_t i=0;i<sizeof(tests)/sizeof(tests[0]);i++) {
    if (tests[i]()) return 1;
    printf("PASS %s\n",names[i]);
  }
  printf("PASS all 9 groups\n");
  return 0;
}
