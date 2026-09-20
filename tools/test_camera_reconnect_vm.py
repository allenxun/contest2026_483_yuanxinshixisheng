"""Exercise actual camera class callbacks with a bounded ownership fixture."""
import base64
from cloud_radio_stage_audit import ROOT, remote
source=(ROOT/'app/k7host/k7host_main.c').read_text()
body=source[source.index('static int connect_camera('):source.index('static const struct usbhost_id_s g_id')]
stub=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
struct usbhost_hubport_s {unsigned funcaddr,speed;};
struct usbhost_id_s {unsigned vid,pid;};
struct usbhost_class_s {struct usbhost_hubport_s *hport;
 int (*connect)(struct usbhost_class_s *,const uint8_t *,int);
 int (*disconnected)(struct usbhost_class_s *);};
static int g_lock,allocations;
static bool g_created,g_connected,g_committed,g_capture_attempted;
static struct usbhost_class_s *g_camera_class;
static uint8_t g_desc[2048];static int g_desclen;
static struct usbhost_hubport_s *g_camera_hport,g_camera_port;
typedef int irqstate_t;
static int enter_critical_section(void){return 0;}
static void leave_critical_section(int f){(void)f;}
static void nxmutex_lock(int *m){assert(!*m);*m=1;}
static int nxmutex_trylock(int *m){if(*m)return -EBUSY;*m=1;return 0;}
static void nxmutex_unlock(int *m){assert(*m);*m=0;}
static void *kmm_zalloc(size_t n){void *p=calloc(1,n);if(p)allocations++;return p;}
static void kmm_free(void *p){assert(p);allocations--;free(p);}
'''
test=r'''
int main(void){
 struct usbhost_hubport_s port={2,3};
 struct usbhost_id_s id={0x32e6,0x9221},wrong={1,2};
 uint8_t desc[9]={9,2};
 assert(!create_camera(&port,&wrong));
 for(int i=0;i<100;i++){
  struct usbhost_class_s *c=create_camera(&port,&id);assert(c);
  assert(!create_camera(&port,&id));
  assert(connect_camera(c,desc,9)==0 && g_connected);
  g_committed=true;g_lock=1;
  assert(disconnect_camera(c)==0); /* Must not wait for the I/O owner. */
  assert(!g_connected && !g_committed && !g_created && allocations==0);
  assert(!create_camera(&port,&id));
  g_lock=0;
 }
 struct usbhost_class_s *c=create_camera(&port,&id);assert(c);
 desc[0]=0;assert(connect_camera(c,desc,9)==-EINVAL);
 disconnect_camera(c);assert(allocations==0);
 g_capture_attempted=true;assert(!create_camera(&port,&id));
 puts("camera pre-capture reconnect ownership passed");return 0;
}
'''
raw=base64.b64encode((stub+body+test).encode()).decode()
print(remote('''import pathlib,tempfile,subprocess,base64
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d);(p/'test.c').write_bytes(base64.b64decode(%r))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11',opt,'-Wall','-Wextra','test.c','-o','test'],cwd=p,check=True)
  r=subprocess.run([str(p/'test')],capture_output=True,text=True,check=True)
  print(opt,r.stdout.splitlines()[-1])
'''%raw).decode())
