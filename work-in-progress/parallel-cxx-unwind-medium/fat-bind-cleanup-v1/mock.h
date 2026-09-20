#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#define FAR
#define OK 0
#define FSTYPE_FAT32 2
#define MNT_FORCE 1
#define UMOUNT_FORCED 1
#define PART_GETTYPE(i,b) ((void)(i),(void)(b),0)
#define PART_ENTRY(i) (i)
#define PART_GETSTARTSECTOR(i,b) ((void)(i),(void)(b),0)
#define finfo(...) ((void)0)
#define ferr(...) ((void)0)
struct inode;
struct geometry {bool geo_available,geo_writeenabled;unsigned geo_sectorsize,geo_nsectors;};
struct bops {int (*open)(struct inode*);int (*close)(struct inode*);int (*geometry)(struct inode*,struct geometry*);};
struct inode {union{struct bops *i_bops;}u;int i_crefs;};
struct fat_file_s {int ff_bflags;struct fat_file_s *ff_next;};
struct fat_mountpt_s {struct inode *fs_blkdriver;int fs_lock;bool fs_mounted;unsigned fs_hwsectorsize,fs_hwnsectors;uint8_t *fs_buffer;off_t fs_fatbase;int fs_type;struct fat_file_s *fs_head;};
static int fail_kind,opened,closed,live,io_live,locks,open_error,close_error;
static int mock_open(struct inode*i){(void)i;opened++;return open_error;}
static int mock_close(struct inode*i){(void)i;closed++;return close_error;}
static int mock_geo(struct inode*i,struct geometry*g){(void)i;if(fail_kind==2)return -EIO;*g=(struct geometry){true,true,512,1000};return 0;}
static void *fs_heap_zalloc(size_t n){void*p;if(fail_kind==1)return NULL;p=calloc(1,n);assert(p);live++;return p;}
static void fs_heap_free(void*p){assert(p);live--;free(p);}
static void *fat_io_alloc(size_t n){void*p;if(fail_kind==3)return NULL;p=malloc(n);assert(p);io_live++;return p;}
static void fat_io_free(void*p,size_t n){(void)n;assert(p);io_live--;free(p);}
static void nxmutex_init(int*l){*l=0;locks++;}
static void nxmutex_destroy(int*l){(void)l;locks--;}
static int nxmutex_lock(int*l){assert(!*l);*l=1;return 0;}
static void nxmutex_unlock(int*l){assert(*l);*l=0;}
static int fat_hwread(struct fat_mountpt_s*f,uint8_t*b,off_t s,unsigned n){(void)f;(void)b;(void)s;(void)n;return fail_kind==4?-EIO:0;}
static int fat_checkbootrecord(struct fat_mountpt_s*f){f->fs_type=FSTYPE_FAT32;return fail_kind==5?-EINVAL:0;}
static int fat_checkfsinfo(struct fat_mountpt_s*f){(void)f;return fail_kind==6?-EILSEQ:0;}
