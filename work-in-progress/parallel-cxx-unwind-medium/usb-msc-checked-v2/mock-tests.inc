struct event { ssize_t result; size_t requested; int ep; int kind; };
static struct event events[4];
static size_t event_count,event_index;
static uint32_t wire_tag,last_lba,sector_size;
static int corrupt_tag,corrupt_sig,residue,status;
static uint8_t captured_opcode;
static ssize_t mock_transfer(void *drvr,int ep,uint8_t *data,size_t len)
{
  struct event *e;
  (void)drvr;
  assert(event_index<event_count);
  e=&events[event_index++]; assert(e->ep==ep && e->requested==len);
  if (e->kind==0) { wire_tag=usbhost_getle32(data+4); captured_opcode=data[15]; }
  if (e->result>=0 && e->kind==1) {
    memset(data,0xa5,(size_t)e->result);
    if (len==8) { usbhost_putbe32(data,last_lba); usbhost_putbe32(data+4,sector_size); }
  }
  if (e->result>=0 && e->kind==2) {
    uint8_t csw[13]={0};
    usbhost_putle32(csw,corrupt_sig?0:0x53425355);
    usbhost_putle32(csw+4,wire_tag+(uint32_t)corrupt_tag);
    usbhost_putle32(csw+8,(uint32_t)residue); csw[12]=(uint8_t)status;
    memcpy(data,csw,(size_t)e->result);
  }
  return e->result;
}
static struct usbhost_state_s device;
static struct usbhost_hubport_s port;
static struct inode node;
static uint8_t tbuffer[64],data_buffer[4096];
static unsigned tests;
static void fresh(void)
{
  memset(&device,0,sizeof(device));
  device.usbclass.hport=&port; device.tbuffer=tbuffer; device.tbuflen=sizeof(tbuffer);
  device.bulkin=1; device.bulkout=2; device.blocksize=512; device.nblocks=1000;
  node.i_private=&device; event_count=event_index=0;
  corrupt_tag=corrupt_sig=residue=status=0; last_lba=999; sector_size=512;
}
static void plan(size_t bytes)
{
  event_count=0; event_index=0;
  events[event_count++]=(struct event){31,31,2,0};
  if(bytes) events[event_count++]=(struct event){(ssize_t)bytes,bytes,1,1};
  events[event_count++]=(struct event){13,13,1,2};
}
static void closed(void)
{
  size_t before=event_index; struct geometry geo;
  assert(device.bot_failed);
  assert(usbhost_read(&node,data_buffer,0,1)==-ENODEV);
  assert(usbhost_geometry(&node,&geo)==-ENODEV && !geo.geo_available);
  assert(event_index==before); tests++;
}
int main(void)
{
  struct geometry geo; ssize_t ret; size_t before;
  fresh(); plan(512); assert(usbhost_read(&node,data_buffer,0,1)==1); assert(event_index==3 && captured_opcode==0x28); tests++;
  assert(usbhost_geometry(&node,&geo)==0 && !geo.geo_writeenabled); tests++;
  before=event_index; assert(usbhost_write(&node,data_buffer,0,1)==-EROFS && event_index==before); tests++;
  /* Negative/oversized requests never issue any USB transfer or poison BOT. */
  fresh(); assert(usbhost_read(&node,data_buffer,-1,1)==-EINVAL && event_index==0); tests++;
  assert(usbhost_read(&node,data_buffer,999,2)==-EINVAL && event_index==0); tests++;
  assert(usbhost_read(&node,data_buffer,0,9)==-EINVAL && event_index==0); tests++;
  assert(usbhost_read(&node,data_buffer,0,65536)==-EINVAL && event_index==0); tests++;
  assert(usbhost_read(&node,data_buffer,0,0)==-EINVAL && event_index==0); tests++;
  assert(!device.bot_failed);
  fresh(); plan(4096); assert(usbhost_read(&node,data_buffer,0,8)==8); tests++;
  fresh(); plan(512); events[0].result=30; assert(usbhost_read(&node,data_buffer,0,1)<0 && event_index==1); closed();
  fresh(); plan(512); events[1].result=511; assert(usbhost_read(&node,data_buffer,0,1)<0 && event_index==2); closed();
  fresh(); plan(512); events[2].result=12; assert(usbhost_read(&node,data_buffer,0,1)<0 && event_index==3); closed();
  fresh(); plan(512); corrupt_tag=1; assert(usbhost_read(&node,data_buffer,0,1)<0); closed();
  fresh(); plan(512); corrupt_sig=1; assert(usbhost_read(&node,data_buffer,0,1)<0); closed();
  fresh(); plan(512); residue=1; assert(usbhost_read(&node,data_buffer,0,1)<0); closed();
  fresh(); plan(512); status=1; assert(usbhost_read(&node,data_buffer,0,1)<0); closed();
  fresh(); plan(512); events[0].result=-EAGAIN; assert(usbhost_read(&node,data_buffer,0,1)==-EIO && event_index==1); closed();
  fresh(); plan(512); events[1].result=-EAGAIN; assert(usbhost_read(&node,data_buffer,0,1)==-EIO && event_index==2); closed();
  fresh(); plan(8); assert(usbhost_readcapacity(&device)==0 && device.nblocks==1000 && device.blocksize==512); tests++;
  fresh(); plan(8); last_lba=UINT32_MAX; assert(usbhost_readcapacity(&device)<0); closed();
  fresh(); plan(8); sector_size=65536; assert(usbhost_readcapacity(&device)<0); closed();
  fresh(); plan(8); events[1].result=7; assert(usbhost_readcapacity(&device)<0); closed();
  fresh(); plan(8); corrupt_tag=1; assert(usbhost_readcapacity(&device)<0); closed();
  /* IN data overwrites CBW.tag in shared tbuffer. Saved wire tag must win. */
  fresh(); plan(36); ret=usbhost_inquiry(&device); assert(ret==0 && wire_tag==1 && event_index==3); tests++;
  plan(18); assert(usbhost_requestsense(&device)==0 && wire_tag==2); tests++;
  plan(0); assert(usbhost_testunitready(&device)==0 && wire_tag==3); tests++;
  fresh(); plan(0); status=1; assert(usbhost_testunitready(&device)==0 && !device.bot_failed && tbuffer[12]==1); tests++;
  fresh(); plan(0); status=2; assert(usbhost_testunitready(&device)<0); closed();
  fresh(); plan(18); events[2].result=12; assert(usbhost_requestsense(&device)<0); closed();
  fresh(); plan(36); residue=1; assert(usbhost_inquiry(&device)<0); closed();
  fresh(); device.disconnected=true; assert(usbhost_read(&node,data_buffer,0,1)==-ENODEV && event_index==0); tests++;
  printf("PASS %u real candidate function replay groups; mock transport only\n",tests);
  return 0;
}
