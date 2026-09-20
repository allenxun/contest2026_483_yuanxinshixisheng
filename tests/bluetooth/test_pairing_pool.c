/* Exercise the production allocator with stubbed connection/address helpers. */
#include <assert.h>
#include <stdio.h>
#include "bt_keys.c"
static struct bt_conn_s active;
static int active_present, refs;
struct bt_conn_s *bt_conn_lookup_state(const bt_addr_le_t *addr, int state)
{ (void)addr;(void)state;if (!active_present)return NULL;refs++;return &active; }
void bt_conn_release(struct bt_conn_s *conn)
{ assert(conn==&active);refs--; }
static bt_addr_le_t peer(unsigned int n)
{ bt_addr_le_t p={.type=1,.val={0}};p.val[0]=n;return p; }
static void reset(void)
{
  memset(g_key_pool,0,sizeof(g_key_pool));
  g_ltks=g_slave_ltks=g_irks=g_local_csrks=g_remote_csrks=NULL;
  active_present=0;refs=0;
#ifdef CONFIG_BLUETOOTH_RECYCLE_IDLE_KEYS
  g_recycle_next=0;
#endif
}
int main(void)
{
  bt_addr_le_t a=peer(1),b=peer(2),c=peer(3),d=peer(4);
  struct bt_keys_s *ka,*kb,*kc,*kd;
  reset();ka=bt_keys_get_type(BT_KEYS_SLAVE_LTK,&a);
  kb=bt_keys_get_type(BT_KEYS_IRK,&b);
  assert(ka&&kb&&ka!=kb);
  bt_keys_clear(ka,BT_KEYS_ALL);
  assert(bt_keys_get_addr(&b)==kb); /* Hole must not duplicate existing peer. */
  ka=bt_keys_get_type(BT_KEYS_SLAVE_LTK,&a);
  kc=bt_keys_get_type(BT_KEYS_LTK,&c);assert(kc);
  bt_keys_add_type(ka,BT_KEYS_IRK);bt_keys_add_type(ka,BT_KEYS_LTK);
  bt_keys_add_type(ka,BT_KEYS_LOCAL_CSRK);bt_keys_add_type(ka,BT_KEYS_REMOTE_CSRK);
  memset(ka->slave_ltk.val,0xa5,sizeof(ka->slave_ltk.val));
  active_present=1;active.keys=ka;active.dst=peer(99); /* Protect by key pointer even with an RPA. */
  kd=bt_keys_get_addr(&d);
#ifdef CONFIG_BLUETOOTH_RECYCLE_IDLE_KEYS
  assert(kd&&kd!=ka);assert(bt_keys_find(BT_KEYS_SLAVE_LTK,&a)==ka);
  assert(bt_keys_find(BT_KEYS_IRK,&b)==NULL);assert(refs==0);
  active.keys=NULL;active.dst=a; /* Protect address even before keys attach. */
  for (unsigned int n=5;n<30;n++)
    { bt_addr_le_t p=peer(n);assert(bt_keys_get_type(BT_KEYS_LTK,&p));assert(bt_keys_get_addr(&a)==ka); }
  active_present=0;
  for (unsigned int n=30;n<34;n++)
    { bt_addr_le_t p=peer(n);assert(bt_keys_get_addr(&p)); }
  assert(bt_keys_find(BT_KEYS_SLAVE_LTK,&a)==NULL);
  assert(bt_keys_find(BT_KEYS_IRK,&a)==NULL);
  assert(bt_keys_find(BT_KEYS_LTK,&a)==NULL);
  assert(bt_keys_find(BT_KEYS_LOCAL_CSRK,&a)==NULL);
  assert(bt_keys_find(BT_KEYS_REMOTE_CSRK,&a)==NULL);
  for (unsigned int i=0;i<sizeof(ka->slave_ltk.val);i++)assert(ka->slave_ltk.val[i]==0);
  assert(refs==0);
#else
  assert(kd==NULL);assert(bt_keys_find(BT_KEYS_IRK,&b)==kb);
#endif
  puts("PASS: existing peer after hole; pool full policy; active key/address protection; recycle cleanup");
}
