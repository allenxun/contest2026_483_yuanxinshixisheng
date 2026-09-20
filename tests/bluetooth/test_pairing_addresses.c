/* The runner inserts the actual production address-selection function. */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define FAR
#define BT_HCI_ROLE_MASTER 0
#define BT_HCI_ROLE_SLAVE 1
typedef struct { uint8_t type;uint8_t val[6]; } bt_addr_le_t;
struct bt_conn_s { uint8_t role;bt_addr_le_t src,dst,dst_on_air; };
/* PRODUCTION_ADDRESS_HELPER */
int main(void)
{
  struct bt_conn_s conn={0};
  const bt_addr_le_t local={0,{1,2,3,4,5,6}};
  const bt_addr_le_t wire={1,{7,8,9,10,11,0x42}};
  const bt_addr_le_t identity={0,{21,22,23,24,25,26}};
  const bt_addr_le_t *ia,*ra;
  conn.src=local;conn.dst_on_air=wire;conn.dst=identity;
  for (int role=0;role<2;role++)
    {
      conn.role=role;smp_pairing_addresses(&conn,&ia,&ra);
      const bt_addr_le_t *remote=role==BT_HCI_ROLE_MASTER?ra:ia;
      const bt_addr_le_t *own=role==BT_HCI_ROLE_MASTER?ia:ra;
      assert(!memcmp(remote,&wire,sizeof(wire)));
      assert(memcmp(remote,&identity,sizeof(identity))!=0);
      assert(!memcmp(own,&local,sizeof(local)));
      assert(!memcmp(&conn.dst,&identity,sizeof(identity))); /* Bond lookup identity stays intact. */
      conn.dst=wire;smp_pairing_addresses(&conn,&ia,&ra);
      assert(!memcmp(role==0?ra:ia,&wire,sizeof(wire))); /* First pairing without IRK. */
      conn.dst=identity;
    }
  puts("PASS: both roles preserve on-air address/type after identity resolution; first pairing unchanged");
}
