#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#undef O_RDONLY
#undef O_WRONLY
#undef O_RDWR
#undef O_ACCMODE
#undef O_CREAT
#undef O_EXCL
#undef O_APPEND
#undef O_TRUNC
/* Exact numeric values from frozen NuttX fcntl.h. */
#define O_RDONLY 1
#define O_RDOK 1
#define O_WRONLY 2
#define O_RDWR 3
#define O_ACCMODE 3
#define O_CREAT 4
#define O_EXCL 8
#define O_APPEND 16
#define O_TRUNC 32
#define SEC_NDXMASK(fs) ((fs)->fs_hwsectorsize-1)
#define FAR
#define OK 0
#define FFBUFF_VALID 1
#define FFBUFF_DIRTY 2
#define FFBUFF_MODIFIED 4
#define UMOUNT_FORCED 8
#define FSTYPE_FAT12 0
#define FSTYPE_FAT16 1
#define FSTYPE_FAT32 2
#define FAT_GETFAT16(b,o) ((uint16_t)((b)[o]|((b)[(o)+1]<<8)))
#define FAT_GETFAT32(b,o) ((uint32_t)FAT_GETFAT16(b,o)|((uint32_t)FAT_GETFAT16(b,(o)+2)<<16))
#define MNT_FORCE 1
#define finfo(...) ((void)0)
#define ferr(...) ((void)0)
#define DEBUGASSERT(x) ((void)0)
#define PART_GETTYPE(i,b) 0
#define PART_GETSTARTSECTOR(i,b) 0
#define PART_ENTRY(i) 0
struct geometry {bool geo_available,geo_writeenabled,geo_mediachanged;size_t geo_sectorsize,geo_nsectors;};
struct inode;
struct block_operations {
 int (*open)(struct inode*);int (*close)(struct inode*);
 ssize_t (*read)(struct inode*,uint8_t*,off_t,unsigned);
 ssize_t (*write)(struct inode*,const uint8_t*,off_t,unsigned);
 int (*geometry)(struct inode*,struct geometry*);
};
struct inode {void *i_private;union {struct block_operations *i_bops;} u;};
struct fat_file_s {struct fat_file_s *ff_next;uint8_t *ff_buffer;unsigned ff_bflags;off_t ff_cachesector,ff_size,ff_currentsector; unsigned ff_oflags,ff_sectorsincluster;};
struct fat_mountpt_s {
 struct inode *fs_blkdriver;struct fat_file_s *fs_head;uint8_t *fs_buffer;
 bool fs_mounted,fs_dirty,fs_fsidirty;int fs_lock,fs_type;unsigned fs_nclusters,fs_fsifreecount;
 size_t fs_hwsectorsize,fs_hwnsectors;off_t fs_fatbase,fs_currentsector;
};
struct file {struct inode *f_inode;void *f_priv;off_t f_pos;};
struct fat_dirinfo_s;struct fat_dirseq_s;struct fs_fatdir_s;
typedef uint8_t fat_attrib_t;
static unsigned reads,writes,opens,closes,allocs,frees;
static int geo_writable,short_read,read_error,bad_boot;
static void *fs_heap_zalloc(size_t n){void *p=calloc(1,n);if(p)++allocs;return p;}
static void fs_heap_free(void *p){if(p){++frees;free(p);}}
static void *fat_io_alloc(size_t n){return fs_heap_zalloc(n);}
static void fat_io_free(void *p,size_t n){(void)n;fs_heap_free(p);}
static int nxmutex_init(int*p){*p=0;return 0;}
static int nxmutex_lock(int*p){(void)p;return 0;}
static int nxmutex_unlock(int*p){(void)p;return 0;}
static int nxmutex_destroy(int*p){(void)p;return 0;}
static int fat_checkbootrecord(struct fat_mountpt_s *fs){fs->fs_type=FSTYPE_FAT32;fs->fs_nclusters=4;return bad_boot?-EINVAL:0;}
static int fat_checkfsinfo(struct fat_mountpt_s *fs){(void)fs;return 0;}
static int mock_open(struct inode*i){(void)i;++opens;return 0;}
static int mock_close(struct inode*i){(void)i;++closes;return 0;}
static int mock_geometry(struct inode*i,struct geometry*g){(void)i;*g=(struct geometry){true,geo_writable!=0,false,512,64};return 0;}
static ssize_t mock_read(struct inode*i,uint8_t*b,off_t s,unsigned n){(void)i;++reads;if(read_error)return -EIO;if(short_read)return 0;memset(b,(int)(s&255),512*n);return n;}
static ssize_t mock_write(struct inode*i,const uint8_t*b,off_t s,unsigned n){(void)i;(void)b;(void)s;++writes;return n;}
static struct block_operations ops={mock_open,mock_close,mock_read,mock_write,mock_geometry};
static int fat_hwread(struct fat_mountpt_s *,uint8_t *,off_t,unsigned);
static int fat_hwwrite(struct fat_mountpt_s *,uint8_t *,off_t,unsigned);
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line=%d %s\n",__LINE__,#x);return 1;}}while(0)

/* MOCK cluster mapping only; full FAT chain parser is outside host harness. */
static int fat_get_sectors(struct file *f,bool read){struct fat_file_s *ff=f->f_priv;if(!read)return -EROFS;ff->ff_currentsector=8+f->f_pos/512;ff->ff_sectorsincluster=1;return 0;}

static int fat_computefreeclusters(struct fat_mountpt_s *);
static off_t fat_getcluster(struct fat_mountpt_s *fs,uint32_t n){(void)fs;(void)n;return 0;}
