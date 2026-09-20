/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         bsp_gpio.h
* @author       
* @version      V1.0
* @date         
* @brief        gpio头文件
* @details      
* @par History  见如下说明
*                 
* version:	
*/

#ifndef __BSP_GPIO_H__
#define __BSP_GPIO_H__	


#include "stm32f10x.h"


void Servo_GPIO_Init(void);
void Servo_Init(u16 arr,u16 psc);



#endif

