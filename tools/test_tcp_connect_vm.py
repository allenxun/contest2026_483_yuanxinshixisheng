"""Exercise the actual connection helper's timeout/error paths without a board."""
import base64
from cloud_radio_stage_audit import ROOT,remote
source=(ROOT/'app/k7agent/cloud/src/board_speech_bridge.c').read_text()
body='static int connect_server('+source.split('static int connect_server(',1)[1].split('\nstruct live {',1)[0]
pre=r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/time.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
static int scenario,closed;
static int fake_socket(int a,int b,int c){(void)a;(void)b;(void)c;return 7;}
static int fake_fcntl(int fd,int op,...){(void)fd;(void)op;return 0;}
static int fake_connect(int fd,const struct sockaddr *a,socklen_t n){(void)fd;(void)a;(void)n;errno=scenario==4?ENETUNREACH:EINPROGRESS;return -1;}
static int fake_poll(struct pollfd *p,nfds_t n,int t){(void)p;(void)n;(void)t;if(scenario==1)return 0;if(scenario==2){errno=EINTR;return -1;}return 1;}
static int fake_getsockopt(int fd,int l,int o,void *e,socklen_t *n){(void)fd;(void)l;(void)o;(void)n;*(int*)e=scenario==3?ECONNREFUSED:0;return 0;}
static int fake_setsockopt(int fd,int l,int o,const void *v,socklen_t n){(void)fd;(void)l;(void)o;(void)v;(void)n;return 0;}
static int fake_close(int fd){assert(fd==7);closed++;return 0;}
#define socket fake_socket
#define fcntl fake_fcntl
#define connect fake_connect
#define poll fake_poll
#define getsockopt fake_getsockopt
#define setsockopt fake_setsockopt
#define close fake_close
'''
test=pre+body+r'''
int main(void){
assert(connect_server("invalid")==-EINVAL && closed==0);
assert(connect_server("127.0.0.1")==7 && closed==0);
scenario=1;assert(connect_server("127.0.0.1")==-ETIMEDOUT && closed==1);
scenario=2;assert(connect_server("127.0.0.1")==-EINTR && closed==2);
scenario=3;assert(connect_server("127.0.0.1")==-ECONNREFUSED && closed==3);
scenario=4;assert(connect_server("127.0.0.1")==-ENETUNREACH && closed==4);
puts("connect error preservation PASS");
}
'''
print(remote('''import tempfile,pathlib,base64,subprocess
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d);(p/'test.c').write_bytes(base64.b64decode(%r))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',opt,str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
'''%base64.b64encode(test.encode()).decode()).decode())

