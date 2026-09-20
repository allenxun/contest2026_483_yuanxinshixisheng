#include "AllHeader.h"
#include "led.h"


void led_init(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(LED1_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = LED1_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化BEEP_PORT*/
  	GPIO_Init(LED1_PORT, &GPIO_InitStructure);
	
	GPIO_SetBits(LED1_PORT,LED1_PIN);
	
}
