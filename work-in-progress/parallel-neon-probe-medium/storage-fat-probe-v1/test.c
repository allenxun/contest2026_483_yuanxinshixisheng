#define main probe_main
#include "k7fat_main.c"
#undef main
#include <assert.h>
static int mounts, unmounts, closes, mode, reads;
static DIR dir;
static struct dirent ent;
int mount(const char *s,const char *t,const char *f,unsigned long fl,const void *p) {
  assert(!strcmp(s,"/dev/sda") && !strcmp(t,"/mnt/k7model"));
  assert(!strcmp(f,"vfat") && fl==MS_RDONLY && p==NULL); ++mounts;
  if(mode==1){errno=EIO;return -1;} return 0;
}
int umount2(const char *t,unsigned int f) {
  assert(!strcmp(t,"/mnt/k7model") && f==0); ++unmounts;
  if(mode==2){errno=EBUSY;return -1;} return 0;
}
DIR *opendir(const char *s) { assert(!strcmp(s,"/mnt/k7model")); reads=0;
 if(mode==3){errno=EIO;return NULL;} return &dir; }
struct dirent *readdir(DIR *d) {
 assert(d==&dir);
 if(mode==4){errno=EIO;return NULL;}
 if(mode==5){memset(ent.d_name,'a',sizeof ent.d_name);return &ent;}
 if(mode!=6 && reads++) return NULL;
 memset(&ent,0,sizeof ent); strcpy(ent.d_name,"x\n\033"); return &ent;
}
int closedir(DIR *d){assert(d==&dir); ++closes;
 if(mode==7){errno=EIO;return -1;}return 0;}
static int call(char *s){char *a[]={"k7fat",s};return probe_main(2,a);}
static void reset(void){attempted=mounted=directory_uncertain=owner=0;mode=0;}
int main(void) {
 char *bad[]={"k7fat"}; assert(probe_main(1,bad)==1 && mounts==0);
 assert(call("list")==1 && call("unmount")==1);
 mode=1; assert(call("mount")==1 && attempted && !mounted);
 mode=0; assert(call("mount")==1 && mounts==1);
 reset(); assert(!call("mount") && mounted);
 assert(!call("list") && closes==1);
 mode=2; assert(call("unmount")==1 && mounted);
 mode=3; assert(call("list")==1 && closes==1);
 mode=4; assert(call("list")==1 && closes==2);
 mode=5; assert(call("list")==1 && closes==3);
 mode=6; assert(call("list")==1 && closes==4);
 mode=7; assert(call("list")==1 && directory_uncertain);
 assert(call("list")==1 && closes==5);
 mode=0; assert(!call("unmount") && !mounted);
 assert(call("mount")==1);
 owner=1; assert(call("mount")==1); owner=0;
 puts("PASS mock: args/fixed paths/failed mount latch/bounded names+entries/errors/busy/no force");
 return 0;
}
