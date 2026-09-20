#include "E:/openvela/VelaVision/app/k7radio/skw_wifi_amsdu.h"
int baseline(struct skw_amsdu_rx*a,struct skw_data_replay*r,const uint8_t*p,uint64_t time,int(*deliver)(const uint8_t*,size_t)) {
 static const uint8_t own[6]={2,0,0,0,0,1};
 return skw_amsdu_receive(a,r,p,120,0,0,own,time,deliver);
}
