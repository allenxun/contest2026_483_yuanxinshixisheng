#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
/* ABI-shape mock, NOT target headers or a real mount. */
#if OFF_BITS == 64
#define off_t int64_t
#else
#define off_t int32_t
#endif
#define FAR
#define OK 0
#define DEBUGASSERT(x) assert(x)
#define UMOUNT_FORCED 8
#define FATATTR_VOLUMEID 8
#define FATATTR_READONLY 1
#define FATATTR_DIRECTORY 16
#define S_IROTH 4
#define S_IRGRP 32
#define S_IRUSR 256
#define S_IWOTH 2
#define S_IWGRP 16
#define S_IWUSR 128
#define S_IFDIR 0x4000
#define S_IFREG 0x8000
#define DIR_SIZE 32
#define DIRSEC_NDXMASK(fs) (((fs)->fs_hwsectorsize/32)-1)
/* Frozen FAT directory layout, explicit byte accesses for host endian safety. */
static uint16_t u16(const uint8_t*p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t u32(const uint8_t*p){return (uint32_t)u16(p)|((uint32_t)u16(p+2)<<16);}
#define DIR_GETATTRIBUTES(p) ((p)[11])
#define DIR_GETCRTIME(p) u16((p)+14)
#define DIR_GETCRDATE(p) u16((p)+16)
#define DIR_GETLASTACCDATE(p) u16((p)+18)
#define DIR_GETWRTTIME(p) u16((p)+22)
#define DIR_GETWRTDATE(p) u16((p)+24)
#define DIR_GETFILESIZE(p) u32((p)+28)
struct stat {uint64_t st_dev,st_ino;unsigned st_mode;int64_t st_mtime,st_atime,st_ctime;off_t st_size;int64_t st_blksize,st_blocks;};
struct fat_mountpt_s {uint8_t*fs_buffer;int fs_lock;unsigned fs_hwsectorsize,fs_fatsecperclus;};
struct fat_file_s {unsigned ff_bflags,ff_dirindex;off_t ff_size,ff_dirsector;};
struct inode {void*i_private;};
struct file {struct inode*f_inode;void*f_priv;off_t f_pos;};
static int health_error,cache_error,flush_error;
static int nxmutex_lock(int*p){(void)p;return 0;}
static void nxmutex_unlock(int*p){(void)p;}
static int fat_checkmount(struct fat_mountpt_s*f){(void)f;return health_error;}
static int fat_fscacheread(struct fat_mountpt_s*f,off_t n){(void)f;(void)n;return cache_error;}
static int fat_ffcacheflush(struct fat_mountpt_s*f,struct fat_file_s*b){(void)f;(void)b;return flush_error;}
static int64_t fat_fattime2systime(uint16_t t,uint16_t d){(void)t;(void)d;return 0;}
