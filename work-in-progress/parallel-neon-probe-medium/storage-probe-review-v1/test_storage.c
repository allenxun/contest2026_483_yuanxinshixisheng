#define main storage_main
#ifdef FIXED
#include "candidate.c"
#else
#include "input/k7storage_main.c"
#endif
#undef main
#include <assert.h>
static int start_rc,lock_rc,open_rc,geo_rc,close_rc,dir_open_error,dir_read_error,dir_close_error;
static int bad_second,read_rc[2],opened,closed,reads,started,unlocked;
static unsigned dir_count,dir_index,dir_closed;
static struct geometry geo;
static DIR directory;
static struct dirent entry;
static struct inode node;
static ssize_t block_read(struct inode*i,unsigned char*b,uint64_t lba,unsigned n) {
 assert(i==&node&&lba==0&&n==1&&reads<2);int current=reads++;
 if(read_rc[current]!=1)return read_rc[current];
 memset(b,0x22,geo.geo_sectorsize);b[510]=0x55;b[511]=0xaa;
 if(current&&bad_second)b[0]^=1;
 return 1;
}
static int block_geo(struct inode*i,struct geometry*g){assert(i==&node);*g=geo;return geo_rc;}
static const struct block_operations operations={block_read,block_geo};
int rk3576_usbhost_initialize(void){started++;return start_rc;}
int nxmutex_trylock(mutex_t*m){(void)m;return lock_rc;}
int nxmutex_unlock(mutex_t*m){(void)m;unlocked++;return 0;}
int open_blockdriver(const char*p,int flags,struct inode**out){assert(!strcmp(p,"/dev/sda")&&flags==MS_RDONLY);opened++;if(open_rc)return open_rc;*out=&node;return 0;}
int close_blockdriver(struct inode*i){assert(i==&node);closed++;return close_rc;}
DIR* opendir(const char*p){assert(!strcmp(p,"/dev"));if(dir_open_error){errno=EIO;return NULL;}return &directory;}
struct dirent* readdir(DIR*d){assert(d==&directory);if(dir_index==dir_count){if(dir_read_error)errno=EIO;return NULL;}dir_index++;strcpy(entry.d_name,dir_index==1?"sda":"other");return &entry;}
int closedir(DIR*d){assert(d==&directory);dir_closed++;if(dir_close_error){errno=EIO;return -1;}return 0;}
static void reset(void){
 start_rc=lock_rc=open_rc=geo_rc=close_rc=dir_open_error=dir_read_error=dir_close_error=0;
 bad_second=opened=closed=reads=started=unlocked=0;read_rc[0]=read_rc[1]=1;
 dir_count=dir_index=dir_closed=0;geo=(struct geometry){.geo_available=true,.geo_nsectors=2048,.geo_sectorsize=512};node.u.i_bops=&operations;
}
static int call(const char*cmd,const char*path){char*a[]={"k7storage",(char*)cmd,(char*)path};return storage_main(path?3:2,a);}
int main(void){
 reset();assert(!call("start",NULL)&&started==1&&!opened&&unlocked==1);
 reset();start_rc=-EIO;assert(call("start",NULL)==1);
 reset();assert(call("read",NULL)==1&&!opened&&!unlocked);
 reset();assert(call("list","/dev/sda")==1&&!opened);
 reset();assert(call("read","/dev/mmcsd0")==1&&!opened);
 reset();assert(call("read","/dev/sda1")==1&&!opened);
 reset();lock_rc=-EBUSY;assert(call("start",NULL)==1&&!started&&!unlocked);
 reset();assert(!call("list",NULL)&&dir_closed==1);
 reset();dir_count=3;assert(!call("list",NULL)&&dir_index==3&&dir_closed==1);
 reset();dir_open_error=1;assert(call("list",NULL)==1&&!dir_closed);
 reset();dir_read_error=1;assert(call("list",NULL)==
#ifdef FIXED
 1
#else
 0
#endif
 );assert(dir_closed==1);
 reset();dir_close_error=1;assert(call("list",NULL)==
#ifdef FIXED
 1
#else
 0
#endif
 );
#ifdef FIXED
 reset();dir_count=1000;assert(call("list",NULL)==1&&dir_index==256&&dir_closed==1);
#endif
 for(unsigned sector=512;sector<=4096;sector*=2){reset();geo.geo_sectorsize=sector;assert(!call("read","/dev/sda")&&reads==2&&closed==1);}
 reset();open_rc=-ENOENT;assert(call("read","/dev/sda")==1&&!closed&&!reads);
 reset();node.u.i_bops=NULL;assert(call("read","/dev/sda")==1&&closed==1&&!reads);
 reset();geo_rc=-EIO;assert(call("read","/dev/sda")==1&&closed==1&&!reads);
 reset();geo.geo_writeenabled=true;assert(call("read","/dev/sda")==1&&!reads&&closed==1);
 reset();geo.geo_available=false;assert(call("read","/dev/sda")==1&&!reads);
 reset();geo.geo_nsectors=0;assert(call("read","/dev/sda")==1&&!reads);
 reset();geo.geo_sectorsize=8192;assert(call("read","/dev/sda")==1&&!reads);
 reset();geo.geo_sectorsize=-1;assert(call("read","/dev/sda")==1&&!reads);
 reset();read_rc[0]=0;assert(call("read","/dev/sda")==1&&reads==1&&closed==1);
 reset();read_rc[1]=0;assert(call("read","/dev/sda")==1&&reads==2&&closed==1);
 reset();read_rc[0]=-EIO;assert(call("read","/dev/sda")==1&&closed==1);
 reset();bad_second=1;assert(call("read","/dev/sda")==1&&reads==2&&closed==1);
 reset();close_rc=-EIO;assert(call("read","/dev/sda")==1&&reads==2&&closed==1);
 puts("MOCK PASS parameters/start/list/read/geometry/short-read/mismatch/close; no target/device calls");
}
