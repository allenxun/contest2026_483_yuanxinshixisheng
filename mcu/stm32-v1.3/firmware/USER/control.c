#include "control.h"
#include "kalman.h"
#include "AllHeader.h"
#include "bsp_usart.h"
#include "pid.h"
#include "kalman.h"

uint8_t mode_flag = 0;
uint16_t rec_step_point[4][2] = {0};
uint16_t rec_step_p[1][2]= {0};
uint16_t rec_hand[1][4] = {0};
uint8_t step_flag = 0;


int abs(int x)
{
    return x < 0 ? -x : x;
}

void set_target(float x, float y)
{
    x_pid.Target = x;
    y_pid.Target = y;
}



void mode_1(void)
{
    get_point2_p();
    Servo_ApplyLegacy((int16_t)rec_step_p[0][0], (int16_t)rec_step_p[0][1]);
}



void go_to_point(uint16_t now_x, uint16_t now_y, uint16_t targ_x, uint16_t targ_y)
{
    uint16_t i;
    float step_num = 100;/* 250�� */
    float step_x, step_y; /* ����ֵ  */
    float going_x = now_x, going_y = now_y; /* ��ǰĿ��ֵ*/
    
    step_x = (targ_x - now_x) / step_num;
    step_y = (targ_y - now_y) / step_num;

    for(i = 0; i < step_num;){

			
        
			kfp_x.source = step_x;
			kfp_y.source = step_y;
			kfp_x.out = KalmanFilter(&kfp_x, kfp_x.source);
			kfp_y.out = KalmanFilter(&kfp_y, kfp_y.source);
	
			i++;
			going_x += kfp_x.out;
      going_y += kfp_y.out;
				
      set_target(going_x, going_y); 
//		 }
        //printf("x:%d y:%d\r\n", (uint16_t)(going_x+0.5f), (uint16_t)(going_y+0.5f));
        //printf("in for\r\n ");
    }
}

void go_to(uint16_t now_x, uint16_t now_y, uint16_t targ_x, uint16_t targ_y)
{
    uint16_t i;
    float step_num = 100;/* 250�� */
    float step_x, step_y; /* ����ֵ  */
    float going_x = now_x, going_y = now_y; /* ��ǰĿ��ֵ*/
    
    step_x = (targ_x - now_x) / step_num;
    step_y = (targ_y - now_y) / step_num;

    for(i = 0; i < step_num;i++){

        
			kfp_x.source = step_x;
			kfp_y.source = step_y;
			kfp_x.out = KalmanFilter(&kfp_x, kfp_x.source);
			kfp_y.out = KalmanFilter(&kfp_y, kfp_y.source);
	
		
			going_x += kfp_x.out;
      going_y += kfp_y.out;
				
      set_target(-going_x, -going_y); 


    }
}



uint8_t get_active()
{
uint8_t lable ,ret=0;
	if(DataDecode2(&Uart3_RingBuff,&lable) == 0){ 
		 if(lable == 0x00){
				rec_step_p[0][0] =1;
		 }
		 
		 else if(lable ==0xff){
			 rec_step_p[0][1] =1;
	
		 }
	}

return ret;
}



uint8_t get_hand()
{
uint8_t lable ,ret=0;
	if(DataDecode2(&Uart3_RingBuff,&lable) == 0){ 
		 if(lable == 0x00){
				rec_hand[0][0] = 1;
		 }
		 
		 else if(lable == 0x11){
			 rec_hand[0][1] = 1;
			 
		 }
			else if(lable == 0x22){
			
			rec_hand[0][2] = 1;
			
			}
			
			else if(lable == 0xff){
			
			rec_hand[0][3] = 1;
			
			}
	
	}

return ret;
}
uint8_t get_point2_p(void)
{
    uint8_t axis, lo, hi, reserved;
    uint8_t received = 0;
    uint16_t budget;
    /* Bounded drain: favor recent targets over an ever-growing old-command queue. */
    for (budget = 0; budget < RINGBUFF_LEN; ++budget) {
        if (Uart3_RingBuff.Lenght == 0) break;
        if (DataDecode1(&Uart3_RingBuff, &axis, &lo, &hi, &reserved) == 0) {
            rec_step_p[0][axis == 0xff ? 1 : 0] = (uint16_t)(lo | ((uint16_t)hi << 8));
            received = 1;
        }
    }
    return received;
}

