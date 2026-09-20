#include "AllHeader.h"
#include "control.h"

u8 grop = 0;
float version = 1.3;

int main(void)
{
    bsp_init();
    while (1) {
        mode_1();
    }
}
