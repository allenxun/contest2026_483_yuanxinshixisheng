#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#define RINGBUFF_LEN 500
#define RINGBUFF_OK 1
#define RINGBUFF_ERR 0
typedef struct { volatile uint16_t Head, Tail, Lenght; uint8_t Ring_data[500]; } RingBuff_t;
static uint32_t mask;
static uint32_t __get_PRIMASK(void) { return mask; }
static void __disable_irq(void) { mask = 1; }
static void __set_PRIMASK(uint32_t value) { mask = value; }
typedef struct { uint16_t pwm, MAXPWM, MINPWM, MIDPWM; } ServTypdef;
static ServTypdef Xserv = {1492,2500,500,1492}, Yserv = {700,2300,500,700};
static uint16_t cx=1492, cy=700;
static int udis;
#define TIM2 2
#define ENABLE 1
#define DISABLE 0
static void TIM_UpdateDisableConfig(int timer, int state) { (void)timer; udis=state; }
static void TIM_SetCompare1(int timer, uint16_t v) { (void)timer; assert(udis); cx=v; }
static void TIM_SetCompare2(int timer, uint16_t v) { (void)timer; assert(udis); cy=v; }

void RingBuff_Init(RingBuff_t *ringbuff)
{
  //???????
  ringbuff->Head = 0;
  ringbuff->Tail = 0;
  ringbuff->Lenght = 0;
}
uint8_t Write_RingBuff(RingBuff_t *ringbuff, uint8_t data)
{
    uint32_t key = __get_PRIMASK();
    __disable_irq();
    if (ringbuff->Lenght >= RINGBUFF_LEN) {
        __set_PRIMASK(key);
        return RINGBUFF_ERR;
    }
    ringbuff->Ring_data[ringbuff->Tail] = data;
    ringbuff->Tail = (ringbuff->Tail + 1) % RINGBUFF_LEN;
    ringbuff->Lenght++;
    __set_PRIMASK(key);
    return RINGBUFF_OK;
}
uint8_t Read_RingBuff(RingBuff_t *ringbuff, uint8_t *data)
{
    uint32_t key = __get_PRIMASK();
    __disable_irq();
    if (ringbuff->Lenght == 0) {
        __set_PRIMASK(key);
        return RINGBUFF_ERR;
    }
    *data = ringbuff->Ring_data[ringbuff->Head];
    ringbuff->Head = (ringbuff->Head + 1) % RINGBUFF_LEN;
    ringbuff->Lenght--;
    __set_PRIMASK(key);
    return RINGBUFF_OK;
}
uint8_t DataDecode1(RingBuff_t *ringbuff, uint8_t *axis,
                        uint8_t *lo, uint8_t *hi, uint8_t *reserved)
{
    /* Legacy USART3 stream: 55 AA axis lo hi reserved FA.
     * Sliding window also recovers overlapping headers after damaged frames.
     * This legacy protocol has no checksum; keep this limitation explicit.
     */
    static uint8_t frame[7];
    static uint8_t used;
    uint8_t value;
    uint8_t i;
    if (Read_RingBuff(ringbuff, &value) == RINGBUFF_ERR) return 1;
    frame[used++] = value;
    if (used < sizeof(frame)) return 1;
    if (frame[0] == 0x55 && frame[1] == 0xaa &&
        (frame[2] == 0x00 || frame[2] == 0xff) && frame[6] == 0xfa) {
        *axis = frame[2];
        *lo = frame[3];
        *hi = frame[4];
        *reserved = frame[5];
        used = 0;
        return 0;
    }
    for (i = 0; i < sizeof(frame) - 1; ++i) frame[i] = frame[i + 1];
    used = sizeof(frame) - 1;
    return 1;
}
static uint16_t servo_limit(const ServTypdef *servo, int offset)
{
    int32_t pulse = (int32_t)servo->MIDPWM + offset;
    if (pulse > servo->MAXPWM) pulse = servo->MAXPWM;
    if (pulse < servo->MINPWM) pulse = servo->MINPWM;
    return (uint16_t)pulse;
}
void Servo_ApplyLegacy(int16_t x, int16_t y)
{
    /* Preserve old command polarity/gain. These units are NOT degrees. */
    uint16_t px = servo_limit(&Xserv, -(int32_t)x * 12 / 10);
    uint16_t py = servo_limit(&Yserv, (int32_t)y * 15 / 10);
    uint32_t key;
    if (px == Xserv.pwm && py == Yserv.pwm) return;
    key = __get_PRIMASK();
    __disable_irq();
    /* Suppress preload transfer between the two writes. Pulses keep running. */
    TIM_UpdateDisableConfig(TIM2, ENABLE);
    TIM_SetCompare1(TIM2, px);
    TIM_SetCompare2(TIM2, py);
    TIM_UpdateDisableConfig(TIM2, DISABLE);
    Xserv.pwm = px;
    Yserv.pwm = py;
    __set_PRIMASK(key);
}

static RingBuff_t ring;
static int found;
static uint8_t last_axis;
static int16_t last_value;
static void feed(uint8_t b) {
    uint8_t a, lo, hi, r;
    assert(Write_RingBuff(&ring,b));
    if (DataDecode1(&ring,&a,&lo,&hi,&r)==0) {
        found++; last_axis=a; last_value=(int16_t)(lo | ((uint16_t)hi<<8));
    }
}
static void frame(uint8_t a, int16_t value) {
    uint16_t v=(uint16_t)value;
    feed(0x55); feed(0xaa); feed(a); feed((uint8_t)v);
    feed((uint8_t)(v>>8)); feed(0); feed(0xfa);
}
int main(void) {
    int i, before;
    uint8_t b;
    RingBuff_Init(&ring);
    for(i=0;i<500;i++) assert(Write_RingBuff(&ring,(uint8_t)i));
    assert(!Write_RingBuff(&ring,1));
    for(i=0;i<500;i++) { assert(Read_RingBuff(&ring,&b)); assert(b==(uint8_t)i); }
    assert(!Read_RingBuff(&ring,&b));
    for(i=0;i<2000;i++) {
        mask=i&1;
        assert(Write_RingBuff(&ring,(uint8_t)i)); assert(mask==(uint32_t)(i&1));
        assert(Read_RingBuff(&ring,&b)); assert(mask==(uint32_t)(i&1));
        assert(b==(uint8_t)i);
    }
    mask=0;
    /* All signed command values, fragmented one byte at a time. */
    for(i=-32768;i<=32767;i++) {
        before=found;
        frame((i&1)?0xff:0x00,(int16_t)i);
        assert(found==before+1 && last_value==i);
        assert(last_axis==((i&1)?0xff:0x00));
    }
    /* Noise, overlapping header, truncated frame and bad tail. */
    feed(0x19); feed(0x55);
    before=found; frame(0,30); assert(found==before+1 && last_value==30);
    feed(0x55); feed(0xaa); feed(0);
    before=found; frame(0xff,-30); assert(found==before+1 && last_value==-30);
    feed(0x55); feed(0xaa); feed(0); feed(1); feed(2); feed(0); feed(0);
    before=found; frame(0,0); assert(found==before+1 && last_value==0);
    Servo_ApplyLegacy(30,30); assert(cx==1456 && cy==745);
    Servo_ApplyLegacy(-30,-30); assert(cx==1528 && cy==655);
    Servo_ApplyLegacy(32767,-32768); assert(cx==500 && cy==500);
    Servo_ApplyLegacy(-32768,32767); assert(cx==2500 && cy==2300);
    Servo_ApplyLegacy(0,0); assert(cx==1492 && cy==700);
    for(i=-32768;i<=32767;i++) {
        mask=i&1;
        Servo_ApplyLegacy((int16_t)i,(int16_t)i);
        assert(cx>=500 && cx<=2500 && cy>=500 && cy<=2300);
        assert(mask==(uint32_t)(i&1) && udis==0);
    }
    Servo_ApplyLegacy(-800,0); assert(cx==2452 && cy==700);
    Servo_ApplyLegacy(800,0); assert(cx==532 && cy==700);
    Servo_ApplyLegacy(0,0); assert(cx==1492 && cy==700);
    for(i=-32768;i<=32767;i++) {
        int expected_y = 700 + i*15/10;
        if(expected_y<500) expected_y=500;
        if(expected_y>2300) expected_y=2300;
        Servo_ApplyLegacy(0,(int16_t)i);
        assert(cx==1492 && cy==expected_y);
    }
    puts("PASS: X midpoint and symmetric endpoints; all 65536 Y commands unchanged.");
    puts("PASS: ring full/empty/wrap; interrupt mask preservation; 65536 signed frames;");
    puts("PASS: fragmented/noisy/truncated frame recovery; all signed target PWM limits.");
    return 0;
}
