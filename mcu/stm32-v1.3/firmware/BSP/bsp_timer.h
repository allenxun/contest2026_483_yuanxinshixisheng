/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         bsp_timer.h	
* @version      V1.0
* @brief        定时器初始化
* @details      
* @par History  见如下说明
*                 
* version:		liusen_20170717
*/

#ifndef __BSP_TIMER_H__
#define __BSP_TIMER_H__

#include "stm32f10x.h"

//void TIM1_Int_Init(void);
void TIM1_Int_Init(u16 arr,u16 psc);
void set_time(uint16_t time_ms);
void Timer5_init(void);
#endif

