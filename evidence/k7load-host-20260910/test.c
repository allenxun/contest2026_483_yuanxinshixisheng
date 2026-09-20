#include <stdio.h>
#include "workload.h"
int main(void) { for (unsigned i=0;i<100;i++) if(k7load_batch()!=K7LOAD_EXPECTED) return 1; puts("100 batches matched reference"); return 0; }
