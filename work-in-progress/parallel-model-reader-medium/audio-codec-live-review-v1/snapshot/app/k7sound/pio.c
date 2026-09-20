/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pio.h"
#include <stddef.h>
#include <string.h>
#define BIT(n) (UINT32_C(1)<<(n))
#define GENMASK(h,l) ((UINT32_MAX>>(31-(h))) & (UINT32_MAX<<(l)))
#include "input/rockchip_sai.h"
int pio_summarize(const uint32_t *data,unsigned frames,struct pio_stats*out)
{
  unsigned i,ch;int64_t v;
  if(!data||!out||!frames||frames>PIO_FRAMES)return -22;
  memset(out,0,sizeof *out);
  for(i=0;i<frames;i++)for(ch=0;ch<2;ch++) {
    uint32_t w=data[2*i+ch];
    v=w<=INT32_MAX?(int64_t)w:-1-(int64_t)(UINT32_MAX-w);
    if(!i||v<out->min[ch])out->min[ch]=(int32_t)v;
    if(!i||v>out->max[ch])out->max[ch]=(int32_t)v;
    out->sum[ch]+=v;if(w)out->nonzero[ch]++;
  }
  return 0;
}
static int rd(const struct pio_port*p,uint32_t o,uint32_t*v){return p->read(p->ctx,o,v)?-5:0;}
static int wr(const struct pio_port*p,uint32_t o,uint32_t v){return p->write(p->ctx,o,v)?-5:0;}
static int mod(const struct pio_port*p,uint32_t o,uint32_t mask,uint32_t val)
{uint32_t v;if(rd(p,o,&v))return -5;return wr(p,o,(v&~mask)|(val&mask));}
/* No silent reset on idle/clear timeout. 2307 uses STATUS bits3/2/1. */
static int stop(const struct pio_port*p,int tx)
{
  uint32_t v,bit=tx?SAI_XFER_TXS_MASK:SAI_XFER_RXS_MASK;
  uint32_t idle=tx?SAI_STATUS_TX_IDLE:SAI_STATUS_RX_IDLE;
  uint32_t clr=tx?SAI_CLR_TXC:SAI_CLR_RXC;
  uint64_t start=p->us(p->ctx),now;
  unsigned i;
  if(mod(p,SAI_XFER,bit,0))return -5;
  for(i=0;i<10000;i++) {
    if(rd(p,SAI_STATUS,&v))return -5;
    now=p->us(p->ctx);if(now<start || now-start>=1000)return -110;
    if(v&idle)break;
  }
  if(i==10000)return -110;
  if(mod(p,SAI_CLR,clr,clr))return -5;
  for(i=0;i<10000;i++) {
    if(rd(p,SAI_CLR,&v))return -5;
    now=p->us(p->ctx);if(now<start || now-start>=1000)return -110;
    if(!(v&clr))break;
  }
  if(i==10000)return -110;
  if(mod(p,SAI_XFER,SAI_XFER_CLK_MASK|SAI_XFER_FSS_MASK,0))return -5;
  for(i=0;i<10000;i++) {
    if(rd(p,SAI_STATUS,&v))return -5;
    now=p->us(p->ctx);if(now<start || now-start>=2000)return -110;
    if(v&SAI_STATUS_FS_IDLE)break;
  }
  if(i==10000)return -110;
  /* Keep external mclk running. Caller must allow >=2 BCLK before gating. */
  return 0;
}
int pio_run(const struct pio_port*p,int prepared,uint32_t mclk,int tx,
            uint32_t *capture,unsigned capacity,unsigned frames,struct pio_result*out)
{
  uint32_t v,div,word,mask,value;
  uint64_t start,now;
  int rc=-5;
  if(!out)return -22;
  memset(out,0,sizeof *out);
  if(!p || !p->read || !p->write || !p->us || !p->clocks_started ||
      !p->streams_started || !p->amp_off_fast ||
      (tx && (!p->amplitude || p->amplitude>PIO_MAX_AMPLITUDE)) ||
      (tx!=0 && tx!=1) ||
      !frames || frames>PIO_FRAMES || (tx&&(frames<8||frames>3200)) ||
      (!tx && (!capture || capacity<2*frames)))return out->result=-22;
  if(!prepared)return out->result=-38;
  if(!mclk || mclk%1024000u || (div=mclk/1024000u)>4096)return out->result=-22;
  if(rd(p,SAI_VERSION,&v))return out->result=-5;
  if(v!=SAI_VER_2307)return out->result=-38;
  if(rd(p,SAI_XFER,&v))return out->result=-5;
  if(v&0xf)return out->result=-16;
  if(rd(p,SAI_DMACR,&v))return out->result=-5;
  if(v&(SAI_DMACR_RDE_MASK|SAI_DMACR_TDE_MASK))return out->result=-16;
  if(rd(p,SAI_STATUS,&v))return out->result=-5;
  if((v&14)!=14)return out->result=-16;
  /* Refuse residue instead of attributing old FIFO data to this capture. */
  if(rd(p,tx?SAI_TXFIFOLR:SAI_RXFIFOLR,&v))return out->result=-5;
  if(v&0xffffff)return out->result=-16;
  out->held=1;
  mask=SAI_XCR_START_SEL_MASK|SAI_XCR_EDGE_SHIFT_MASK|SAI_XCR_CSR_MASK|
    SAI_XCR_SJM_MASK|SAI_XCR_FBM_MASK|SAI_XCR_SNB_MASK|SAI_XCR_VDJ_MASK|
    SAI_XCR_SBW_MASK|SAI_XCR_VDW_MASK;
  value=SAI_XCR_EDGE_SHIFT_1|SAI_XCR_CSR(1)|SAI_XCR_SNB(2)|
    SAI_XCR_VDJ_L|SAI_XCR_SBW(32)|SAI_XCR_VDW(32);
  if(mod(p,tx?SAI_TXCR:SAI_RXCR,mask,value))goto done;
  if(mod(p,tx?SAI_TX_SHIFT:SAI_RX_SHIFT,SAI_XSHIFT_RIGHT_MASK,2))goto done;
  if(mod(p,SAI_FSCR,SAI_FSCR_EDGE_MASK|SAI_FSCR_FW_MASK|SAI_FSCR_FPW_MASK,
       SAI_FSCR_EDGE_DUAL|SAI_FSCR_FW(64)|SAI_FSCR_FPW(32)))goto done;
  if(mod(p,SAI_CKR,SAI_CKR_MDIV_MASK|SAI_CKR_MSS_MASK|SAI_CKR_CKP_MASK|SAI_CKR_FSP_MASK,
       SAI_CKR_MDIV(div)))goto done;
  /* Default lane0 -> data0, explicit source header path bit positions. */
  if(mod(p,SAI_PATH_SEL,tx?3u:(3u<<8),0))goto done;
  if(mod(p,SAI_INTCR,SAI_INTCR_TXUIE_MASK|SAI_INTCR_RXOIE_MASK,0))goto done;
  if(mod(p,SAI_INTCR,SAI_INTCR_TXUIC|SAI_INTCR_RXOIC,
         tx?SAI_INTCR_TXUIC:SAI_INTCR_RXOIC))goto done;
  if(mod(p,SAI_XFER,SAI_XFER_CLK_MASK|SAI_XFER_FSS_MASK,
         SAI_XFER_CLK_EN|SAI_XFER_FSS_EN))goto done;
  start=p->us(p->ctx);
  out->activation_result=p->clocks_started(p->ctx);
  now=p->us(p->ctx);
  if(out->activation_result){rc=-5;goto done;}
  if(now<start||now-start>=100000){rc=-110;goto done;}
  if(tx) {
    unsigned i;
    for(i=0;i<16;i++){
      if(wr(p,SAI_TXDR,p->amplitude))goto done;
      out->prefill_words++;
    }
    if(rd(p,SAI_TXFIFOLR,&v))goto done;
    out->max_fifo=v&63;
    if(v!=16){rc=-71;goto done;}
    out->frames=8;
  }
  if(mod(p,SAI_XFER,tx?SAI_XFER_TXS_MASK:SAI_XFER_RXS_MASK,
         tx?SAI_XFER_TXS_EN:SAI_XFER_RXS_EN))goto done;
  start=p->us(p->ctx);
  out->start_result=p->streams_started(p->ctx);
  now=p->us(p->ctx);
  if(out->start_result){rc=-5;goto done;}
  if(now<start||now-start>=100){rc=-110;goto done;}
  start=now;
  for(out->polls=0;out->polls<frames*4096u;out->polls++) {
    now=p->us(p->ctx);
    if(now<start || now-start>=((uint64_t)frames*1000000u/16000u+100000u))
      {rc=-110;goto done;}
    if(rd(p,SAI_INTSR,&v))goto done;
    if(v&(tx?SAI_INTSR_TXUI_ACT:SAI_INTSR_RXOI_ACT)){rc=-75;goto done;}
    if(rd(p,tx?SAI_TXFIFOLR:SAI_RXFIFOLR,&v))goto done;
    if(v&0xffffc0){rc=-71;goto done;}
    v&=63;
    if(v>out->max_fifo)out->max_fifo=v;
    if(tx&&v>16){rc=-71;goto done;}
    if(out->frames==frames) { if(!tx || !v){rc=0;goto done;}continue; }
    if(tx && v<=14) {
      word=(out->frames/32)%2 ? 0u-p->amplitude : p->amplitude;
      if(wr(p,SAI_TXDR,word)||wr(p,SAI_TXDR,word))goto done;
      out->frames++;
    } else if(!tx && v>=2) {
      if(rd(p,SAI_RXDR,&capture[2*out->frames]) ||
         rd(p,SAI_RXDR,&capture[2*out->frames+1]))goto done;
      out->frames++;
    }
  }
  rc=-110;
done:
  {
    uint64_t before=p->us(p->ctx),after;
    out->amp_off_result=p->amp_off_fast(p->ctx);
    after=p->us(p->ctx);
    if(after<before||after-before>=100)out->amp_off_result=-110;
  }
  out->stop_result=stop(p,tx);
  if(!out->stop_result&&!out->amp_off_result)out->held=0;
  out->result=rc?rc:(out->amp_off_result?out->amp_off_result:out->stop_result);
  return out->result;
}
