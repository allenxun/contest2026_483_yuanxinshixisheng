#include <stdint.h>
#include <stddef.h>
#include <sys/types.h>
#include <stdbool.h>
/* Match acquired LARGEFILE types: blkcnt_t uint64, blksize_t int16.
 * NAME_MAX is mock-only 255; no claim of target struct ABI size. */
struct geometry {bool geo_available,geo_mediachanged,geo_writeenabled;uint64_t geo_nsectors;int16_t geo_sectorsize;char geo_model[256];};
struct inode;
struct block_operations {
 ssize_t (*read)(struct inode*,unsigned char*,uint64_t,unsigned);
 int (*geometry)(struct inode*,struct geometry*);
};
struct inode {union {const struct block_operations *i_bops;} u;};
int open_blockdriver(const char*,int,struct inode**);
int close_blockdriver(struct inode*);
