/* Explicit LAN speech test commands. No flash, reboot or Wi-Fi operations. */
#include "capture_stream.h"
#include "stream_ring.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

int k7sound_speak_mono16(const int16_t *, unsigned, unsigned);

static int transfer(int fd, void *buffer, size_t bytes, int writing)
{
  unsigned char *p=buffer;
  while(bytes)
    {
      ssize_t n=writing?send(fd,p,bytes,0):recv(fd,p,bytes,0);
      if(n<0 && errno==EINTR)continue;
      if(n<=0)return -EIO;
      p+=n;bytes-=(size_t)n;
    }
  return 0;
}

static int send_packet(int fd, unsigned char type, void *data, uint32_t size)
{
  unsigned char packet[649]={type,size>>24,size>>16,size>>8,size};
  if(size>644 || (size && !data))return -EINVAL;
  if(size)memcpy(packet+5,data,size);
  return transfer(fd,packet,size+5,1);
}

static int header(int fd, unsigned char *type, uint32_t *size)
{
  unsigned char h[5];int rc=transfer(fd,h,sizeof(h),0);
  if(rc)return rc;
  *type=h[0];*size=((uint32_t)h[1]<<24)|((uint32_t)h[2]<<16)|((uint32_t)h[3]<<8)|h[4];
  return 0;
}

static int connect_server(const char *ip)
{
  struct sockaddr_in a;struct timeval timeout={15,0};
  memset(&a,0,sizeof(a));a.sin_family=AF_INET;a.sin_port=htons(8001);
  if(inet_pton(AF_INET,ip,&a.sin_addr)!=1)return -EINVAL;
  int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -errno;
  int flags=fcntl(fd,F_GETFL,0),rc;
  if(flags<0 || fcntl(fd,F_SETFL,flags|O_NONBLOCK)<0){close(fd);return -EIO;}
  rc=connect(fd,(struct sockaddr *)&a,sizeof(a));
  if(rc<0 && errno==EINPROGRESS)
    {
      struct pollfd p={fd,POLLOUT,0};int error=0;socklen_t n=sizeof(error);
      rc=poll(&p,1,10000);
      if(rc>0 && getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&n)==0 && !error)rc=0;
      else rc=-1;
    }
  if(rc || fcntl(fd,F_SETFL,flags)<0){close(fd);return -EIO;}
  if(setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))<0 ||
     setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout))<0)
    {close(fd);return -EIO;}
  return fd;
}

struct live {
  struct k7_stream_ring ring;
  int fd,done,capture_rc,receive_rc,completed;
};

static void *record(void *arg)
{
  struct live *p=arg;
  p->capture_rc=k7sound_capture_stream(48000,k7_stream_ring_sample,&p->ring);
  __atomic_store_n(&p->done,1,__ATOMIC_RELEASE);return NULL;
}

static int json_event(int fd,char *text,size_t cap)
{
  unsigned char kind;uint32_t n;int rc=header(fd,&kind,&n);
  if(rc || kind!='J' || !n || n>=cap)return -EIO;
  rc=transfer(fd,text,n,0);text[n]=0;return rc;
}

static void *receive_events(void *arg)
{
  struct live *p=arg;char text[8193];int rc;
  while(!(rc=json_event(p->fd,text,sizeof(text))))
    {
      /* The development bridge emits JSON with stable spacing. No text logs. */
      if(strstr(text,"\"type\": \"partial\""))puts("K7CLOUD asr partial_received=1");
      else if(strstr(text,"\"type\": \"final\""))puts("K7CLOUD asr final_received=1");
      else if(strstr(text,"\"type\": \"completed\"")){p->completed=1;break;}
      else {rc=-EIO;break;}
    }
  p->receive_rc=rc;
  if(rc){k7_stream_ring_cancel(&p->ring);shutdown(p->fd,SHUT_RDWR);}
  return NULL;
}

static int asr(int fd)
{
  struct live *p=calloc(1,sizeof(*p));pthread_t capture,receiver;
  pthread_attr_t attr;unsigned char audio[644];char ready[256];
  uint32_t seq=0,count=0;int rc,have_rx=0,have_capture=0;
  if(!p)return -ENOMEM;
  p->fd=fd;
  rc=transfer(fd,(void *)"K7S1A",5,1);
  if(!rc)rc=json_event(fd,ready,sizeof(ready));
  if(!rc && !strstr(ready,"\"type\": \"ready\""))rc=-EIO;
  if(rc){free(p);return rc;}
  rc=pthread_attr_init(&attr);if(rc){free(p);return -rc;}
  rc=pthread_attr_setstacksize(&attr,32768);
  if(!rc){rc=pthread_create(&receiver,&attr,receive_events,p);have_rx=!rc;}
  if(!rc){rc=pthread_create(&capture,&attr,record,p);have_capture=!rc;}
  pthread_attr_destroy(&attr);
  if(rc)rc=-rc;
  while(!rc)
    {
      int got=k7_stream_ring_take(&p->ring,audio+4,&seq);
      if(got<0){rc=got;break;}
      if(got)
        {
          if(seq!=count){rc=-EIO;break;}
          audio[0]=seq;audio[1]=seq>>8;audio[2]=seq>>16;audio[3]=seq>>24;
          rc=send_packet(fd,'A',audio,sizeof(audio));count++;
        }
      else if(__atomic_load_n(&p->done,__ATOMIC_ACQUIRE))
        {
          if(__atomic_load_n(&p->ring.produced,__ATOMIC_ACQUIRE)!=
             __atomic_load_n(&p->ring.consumed,__ATOMIC_RELAXED))continue;
          break;
        }
      else usleep(1000);
    }
  if(rc)k7_stream_ring_cancel(&p->ring);
  if(have_capture)pthread_join(capture,NULL);
  if(!rc)rc=p->capture_rc;
  if(!rc && count!=150)rc=-EIO;
  if(!rc)rc=send_packet(fd,'E',NULL,0);
  if(rc)shutdown(fd,SHUT_RDWR);
  if(have_rx)pthread_join(receiver,NULL);
  if(!rc)rc=p->receive_rc;
  if(!rc && !p->completed)rc=-EIO;
  printf("K7CLOUD asr result=%d frames_sent=%lu completed=%d\n",rc,(unsigned long)count,p->completed);
  free(p);return rc;
}

static int tts(int fd)
{
  char phrase[]="联网成功";unsigned char kind;uint32_t size=0;
  int rc=transfer(fd,(void *)"K7S1T",5,1);void *pcm=NULL;
  if(!rc)rc=send_packet(fd,'T',phrase,sizeof(phrase)-1);
  if(!rc)rc=header(fd,&kind,&size);
  if(!rc && (kind!='D'||!size||size>960000||size%2))rc=-EINVAL;
  if(!rc){pcm=malloc(size);if(!pcm)rc=-ENOMEM;}
  if(!rc)rc=transfer(fd,pcm,size,0);
  if(!rc)rc=k7sound_speak_mono16(pcm,size/2,0);
  printf("K7CLOUD tts result=%d pcm_bytes=%lu\n",rc,(unsigned long)size);
  free(pcm);return rc;
}

int k7cloud_board_speech(const char *mode,const char *ip)
{
  int fd=connect_server(ip);if(fd<0){printf("K7CLOUD connect result=%d\n",fd);return fd;}
  int rc=!strcmp(mode,"asr-live")?asr(fd):tts(fd);
  close(fd);return rc;
}
