#include "wifi_dispatch.h"
#define main original_dispatch_main
#include "input/test_dispatch.c"
#undef main
int main(void){atomic_init(&checks,0);targeted();printf("original targeted checks=%u mock_backend_only\n",atomic_load(&checks));return 0;}
