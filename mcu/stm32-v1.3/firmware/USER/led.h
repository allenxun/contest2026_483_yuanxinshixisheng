#ifndef __LED_H__
#define __LED_H__

#include "delay.h"

#include "stm32f10x.h"
#define LED1 PBout(5)

#define LED1_RCC   RCC_APB2Periph_GPIOC
#define LED1_PORT  GPIOB
#define LED1_PIN   GPIO_Pin_5

void led_init(void);
#endif
