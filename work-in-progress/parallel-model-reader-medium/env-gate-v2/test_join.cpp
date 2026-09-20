#include <pthread.h>
#include <exception>
#include <cstdlib>
#include <cstdio>
#include <cassert>
#include <cerrno>
static int injected;
static int joined(pthread_t t,void **p){int rc=pthread_join(t,p);return rc?rc:injected;}
#define pthread_join joined
static void *work(void *p){return p;}
static void checked(pthread_t hThread){void *res;
      const int ret = pthread_join(hThread, &res);
      if (ret != 0) {
        // Returning would free pool queues still reachable by a live worker.
        // This is a fatal invariant failure, not cancellation/recovery.
        std::terminate();
      }

}
int main(int argc,char**){std::set_terminate([]{std::_Exit(77);});injected=argc>1?EINVAL:0;
pthread_t t;assert(!pthread_create(&t,nullptr,work,nullptr));checked(t);
std::puts("JOIN_PROVEN_RELEASE_ALLOWED");return 0;}
