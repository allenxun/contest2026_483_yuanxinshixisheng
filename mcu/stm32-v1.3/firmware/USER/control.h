#ifndef __CONTROL_H
#define __CONTROL_H


#include "stm32f10x.h"
int GFP_abs(int p);
void mode_1(void);

//uint8_t get_point2_p();    //处理坐标函数
uint8_t get_point1_p();


void go_to(uint16_t now_x, uint16_t now_y, uint16_t targ_x, uint16_t targ_y);


uint8_t get_point2_p();   //处理坐标函数
uint8_t get_active();
uint8_t get_hand();
int abs(int x);




































#endif /* __CONTROL_H */
