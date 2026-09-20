"""ASan/UBSan tests of actual bt_keys.c with only platform helpers stubbed."""
import json,shutil,subprocess
from pathlib import Path
SDK=Path('/home/swl/openvela');ROOT=SDK/'work/velavision-project'
OUT=SDK/'work/velavision-phone-pairing-20260909/pool-test';OUT.mkdir(parents=True,exist_ok=True)
for name in ('nuttx/config.h','debug.h','nuttx/wireless/bluetooth/bt_core.h','nuttx/wireless/bluetooth/bt_hci.h','bt_hcicore.h','bt_smp.h','bt_conn.h'):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "stub.h"\n')
shutil.copyfile(ROOT/'port/tracked/nuttx/wireless/bluetooth/bt_keys.c',OUT/'bt_keys.c')
shutil.copyfile(SDK/'nuttx/wireless/bluetooth/bt_keys.h',OUT/'bt_keys.h')
(OUT/'stub.h').write_text('''#ifndef STUB_H
#define STUB_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#define FAR
#define CONFIG_BLUETOOTH_MAX_PAIRED 3
#define wlinfo(...) ((void)0)
#define wlerr(...) ((void)0)
typedef struct { uint8_t val[6]; } bt_addr_t;
typedef struct { uint8_t type; uint8_t val[6]; } bt_addr_le_t;
static const bt_addr_le_t any={0};
#define BT_ADDR_LE_ANY (&any)
#define bt_addr_le_cmp(a,b) memcmp((a),(b),sizeof(bt_addr_le_t))
#define bt_addr_le_copy(a,b) memcpy((a),(b),sizeof(bt_addr_le_t))
#define bt_addr_cmp(a,b) memcmp((a),(b),sizeof(bt_addr_t))
#define bt_addr_copy(a,b) memcpy((a),(b),sizeof(bt_addr_t))
static inline bool bt_addr_le_is_rpa(const bt_addr_le_t *a){(void)a;return false;}
static inline bool bt_smp_irk_matches(const uint8_t *a,const bt_addr_t *b){(void)a;(void)b;return false;}
struct bt_keys_s;
struct bt_conn_s { struct bt_keys_s *keys;bt_addr_le_t dst; };
#define BT_CONN_CONNECTED 1
struct bt_conn_s *bt_conn_lookup_state(const bt_addr_le_t *,int);
void bt_conn_release(struct bt_conn_s *);
#endif
''')
results=[]
for enabled in (False,True):
    binary=OUT/('recycle-on' if enabled else 'recycle-off')
    cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(OUT)]
    if enabled:cmd+=['-DCONFIG_BLUETOOTH_RECYCLE_IDLE_KEYS=1']
    cmd += [str(ROOT/'tests/bluetooth/test_pairing_pool.c'),'-o',str(binary)]
    subprocess.run(cmd,check=True)
    result=subprocess.run([str(binary)],capture_output=True,text=True)
    results.append(dict(enabled=enabled,exit_code=result.returncode,output=result.stdout+result.stderr))
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
(OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
