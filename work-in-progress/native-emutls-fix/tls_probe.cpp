#include <pthread.h>
#include <sched.h>
#include <cstdio>
#include <cstdint>
namespace {
unsigned destroyed;
struct Value {int number=7;~Value(){__atomic_fetch_add(&destroyed,1u,__ATOMIC_RELAXED);}};
Value&local(){static thread_local Value value;return value;}
void*worker(void*arg){
 const int number=static_cast<int>(reinterpret_cast<intptr_t>(arg));
 if(local().number!=7)return reinterpret_cast<void*>(1);
 local().number=number;
 for(unsigned i=0;i<100;i++){sched_yield();if(local().number!=number)return reinterpret_cast<void*>(2);}
 return nullptr;
}
}
extern "C" int k7_tls_selftest(){
 unsigned before=__atomic_load_n(&destroyed,__ATOMIC_RELAXED);
 if(local().number!=7){std::puts("TLS_CHECK FAIL stale initial value");return 1;}
 local().number=123;
 pthread_t a,b;
 if(pthread_create(&a,nullptr,worker,reinterpret_cast<void*>(101)))return 1;
 if(pthread_create(&b,nullptr,worker,reinterpret_cast<void*>(102))){pthread_join(a,nullptr);return 1;}
 void*x=nullptr,*y=nullptr;int ra=pthread_join(a,&x),rb=pthread_join(b,&y);
 unsigned delta=__atomic_load_n(&destroyed,__ATOMIC_RELAXED)-before;
 bool ok=!ra&&!rb&&!x&&!y&&local().number==123&&delta==2;
 std::printf("TLS_CHECK %s workers=2 destructors=%u main_value=%d\n",ok?"PASS":"FAIL",delta,local().number);
 return ok?0:1;
}
