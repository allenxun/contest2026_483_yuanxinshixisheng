/* SPDX-License-Identifier: Apache-2.0
 * Small actual primitive gate. NOT linked to ORT and NOT inference.
 * Target caller supplies an owned immutable regular file containing ABCD.
 */
#define _POSIX_C_SOURCE 200809L
#include "model_reader.h"
#include <pthread.h>
#include <time.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
static pthread_t probe_thread;
static int probe_live;
static uint32_t probe_value; /* process-lifetime borrow survives join failure */
static void *worker(void *p) { *(uint32_t *)p=0x1234; return NULL; }
int k7env_gate_probe(const char *path) {
 mr_file f=MR_FILE_INIT; unsigned char b[2]={0}; struct timespec a,z,delay={0,1000000};
 pthread_attr_t attr;int rc,clean;
 if(probe_live)return EBUSY; /* caller must retain process; no unsafe reuse */
 rc=mr_open(&f,path,4,4,2);if(rc)return rc;
 rc=mr_seek(&f,1);if(!rc)rc=mr_read_exact(&f,b,2);
 clean=mr_close(&f);if(rc)return rc;if(clean)return clean;
 if(b[0]!='B'||b[1]!='C')return EIO;
 if(clock_gettime(CLOCK_MONOTONIC,&a))return errno?errno:EIO;
 while(nanosleep(&delay,&delay))if(errno!=EINTR)return errno?errno:EIO;
 if(clock_gettime(CLOCK_MONOTONIC,&z))return errno?errno:EIO;
 if(z.tv_sec<a.tv_sec||(z.tv_sec==a.tv_sec&&z.tv_nsec<a.tv_nsec))return EIO;
 rc=pthread_attr_init(&attr);if(rc)return rc;
 rc=pthread_attr_setstacksize(&attr,65536);
 if(!rc){probe_value=0;rc=pthread_create(&probe_thread,&attr,worker,&probe_value);if(!rc)probe_live=1;}
 clean=pthread_attr_destroy(&attr);
 if(rc)return rc;
 rc=pthread_join(probe_thread,NULL);if(rc)return rc;probe_live=0;
 if(clean)return clean;
 if(probe_value!=0x1234)return EIO;
 return 0;
}
#ifdef K7ENV_PROBE_MAIN
int main(int argc,char **argv){if(argc!=2)return 2;int rc=k7env_gate_probe(argv[1]);printf("primitive_gate=%d held=%d (not ORT)\n",rc,probe_live);return rc?1:0;}
#endif
