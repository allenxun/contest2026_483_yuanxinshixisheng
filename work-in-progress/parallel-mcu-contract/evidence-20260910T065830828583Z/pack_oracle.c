#include <stdint.h>
#include <errno.h>
#include <stdio.h>
static int fail(int e){return -e;}
int gimbal_link_pack(uint8_t data[14], int x, int y)
{
  /* Extended wire range is for manually stepped calibration. The tracker
   * and legacy set command retain their own existing bounds.
   */
  if (!data || x < -800 || x > 800 || y < -200 || y > 1030)
    return fail(EINVAL);
  for(int i=0;i<2;i++)
    {
      uint16_t v=(uint16_t)(int16_t)(i ? y:x);
      uint8_t *p=data+i*7;
      p[0]=0x55;p[1]=0xaa;p[2]=i?0xff:0;p[3]=v;p[4]=v>>8;p[5]=0;p[6]=0xfa;
    }
  return 0;
}
int main(void) {
  uint8_t data[14]; int v[4][2]={{10,-10},{-800,-200},{800,1030},{0,0}};
  for(int j=0;j<4;j++){if(gimbal_link_pack(data,v[j][0],v[j][1]))return 1;
    for(int i=0;i<14;i++)printf("%02x",data[i]); puts("");}
  if(gimbal_link_pack(data,801,0)!=-EINVAL)return 2;
  if(gimbal_link_pack(data,0,1031)!=-EINVAL)return 3;
  return 0;
}
