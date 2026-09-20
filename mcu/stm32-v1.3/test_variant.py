from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent

def function(path, signature):
    s = (root / 'firmware' / path).read_bytes().decode('latin1')
    start = s.index(signature)
    end = s.index('{', start) + 1
    depth = 1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}')
        end += 1
    return s[start:end]

parts = ['''#include <stdint.h>
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
''']
for sig in ['void RingBuff_Init(', 'uint8_t Write_RingBuff(', 'uint8_t Read_RingBuff(', 'uint8_t DataDecode1(']:
    parts.append(function('BSP/bsp_usart.c', sig))
for sig in ['static uint16_t servo_limit(', 'void Servo_ApplyLegacy(']:
    parts.append(function('BSP/bsp_servo.c', sig))
parts.append(r'''
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
''')
test = root / 'host_test.c'
test.write_text('\n'.join(parts), encoding='ascii')
exe = root / 'host_test.exe'
gcc = r'D:\software\mingw64\mingw64\bin\gcc.exe'
subprocess.check_call([gcc, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', str(test), '-o', str(exe)])
result = subprocess.check_output([str(exe)]).decode('ascii')
(root / 'host-test.log').write_text(result, encoding='ascii')
print(result)
