/* Host ABI scaffolding only. The tested function bodies are extracted
 * verbatim from candidate usbhost_storage.c, not reimplemented here. */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <sys/types.h>
#define FAR
#define OK 0
#define blkcnt_t int64_t
#define DEBUGASSERT assert
#define uerr(...) ((void)0)
#define uinfo(...) ((void)0)
#define usbhost_dumpcbw(x) ((void)(x))
#define usbhost_dumpcsw(x) ((void)(x))
#define USBMSC_CBW_SIGNATURE 0x43425355u
#define USBMSC_CBW_SIZEOF 31
#define USBMSC_CSW_SIZEOF 13
#define USBMSC_CBWFLAG_IN 0x80
#define SCSIRESP_READCAPACITY10_SIZEOF 8
#define SCSIRESP_INQUIRY_SIZEOF 36
#define SCSIRESP_FIXEDSENSEDATA_SIZEOF 18
#define SCSICMD_READCAPACITY10_SIZEOF 10
#define SCSICMD_READ10_SIZEOF 10
#define SCSICMD_WRITE10_SIZEOF 10
#define SCSICMD_TESTUNITREADY_SIZEOF 6
#define SCSICMD_REQUESTSENSE_SIZEOF 6
#define SCSICMD_INQUIRY_SIZEOF 6
#define SCSI_CMD_READCAPACITY10 0x25
#define SCSI_CMD_READ10 0x28
#define SCSI_CMD_WRITE10 0x2a
#define SCSI_CMD_TESTUNITREADY 0
#define SCSI_CMD_REQUESTSENSE 3
#define SCSI_CMD_INQUIRY 0x12
struct usbmsc_cbw_s { uint8_t signature[4],tag[4],datlen[4],flags,lun,cdblen,cdb[16]; };
struct scsicmd_readcapacity10_s { uint8_t opcode,rest[9]; };
struct scsicmd_requestsense_s { uint8_t opcode,b1,b2,b3,alloclen,b5; };
struct scscicmd_inquiry_s { uint8_t opcode,b1,b2,alloclen[2],b5; };
struct scsicmd_read10_s { uint8_t opcode,b1,lba[4],b6,xfrlen[2],b9; };
struct scsicmd_write10_s { uint8_t opcode,b1,lba[4],b6,xfrlen[2],b9; };
struct usbhost_hubport_s { void *drvr; };
struct usbhost_class_s { struct usbhost_hubport_s *hport; };
struct usbhost_state_s {
  struct usbhost_class_s usbclass;
  bool disconnected,bot_failed;
  uint32_t next_tag,nblocks;
  uint16_t blocksize;
  uint8_t *tbuffer;
  size_t tbuflen;
  int bulkout,bulkin,lock;
};
struct inode { void *i_private; };
struct geometry { bool geo_available,geo_mediachanged,geo_writeenabled; uint64_t geo_nsectors; uint16_t geo_sectorsize; };
static int nxmutex_lock(int *lock) { assert(!*lock); *lock=1; return 0; }
static void nxmutex_unlock(int *lock) { assert(*lock); *lock=0; }
static ssize_t mock_transfer(void *drvr,int ep,uint8_t *data,size_t len);
#define DRVR_TRANSFER mock_transfer
static struct usbmsc_cbw_s *usbhost_cbwalloc(struct usbhost_state_s *priv);
