/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         bsp_gpio.c      
* @version      V1.0       
* @brief        驱动gpio源文件
* @details      
* @par History  见如下说明
*                 
* version:	
*/

#include "AllHeader.h"
#include "pid.h"

/**
* Function       Servo_GPIO_Init
* @author        
* @date            
* @brief         需要用到的舵机初始化接口
* @param[in]     void
* @param[out]    void
* @retval        void
* @par History   无
*/

//void Servo_Init(u16 arr,u16 psc)
//{
//	GPIO_InitTypeDef GPIO_InitStructure;
//	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
//	TIM_OCInitTypeDef  TIM_OCInitStructure;
// 
//	RCC_APB2PeriphClockCmd(RCC_APB2Periph_TIM1, ENABLE); //时钟使能
// 	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA|RCC_APB2Periph_AFIO, ENABLE);  //使能GPIOA外设和AFIO复用功能模块时钟,使能定时器2时钟
// 
//	GPIO_InitStructure.GPIO_Pin =GPIO_Pin_0|GPIO_Pin_1; //TIM2   CH1 PWMA  CH2 PWMB
//	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;  //复用推挽输出
//	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
//	GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化GPIO
//	
// 
//   //初始化TIM2
//	TIM_TimeBaseStructure.TIM_Period = arr; //设置在下一个更新事件装入活动的自动重装载寄存器周期的值	
//	TIM_TimeBaseStructure.TIM_Prescaler = (psc-1); //设置用来作为TIMx时钟频率除数的预分频值
//	TIM_TimeBaseStructure.TIM_ClockDivision = TIM_CKD_DIV1; //设置时钟分割:TDTS = Tck_tim
//	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;  //TIM向上计数模式
//	TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;    //重复计数关闭
////	TIM_TimeBaseInit(TIM1, &TIM_TimeBaseStructure); //根据TIM_TimeBaseInitStruct中指定的参数初始化TIMx的时间基数单位
//	


// 
//// 	TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2;
////	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable;
////	TIM_OCInitStructure.TIM_Pulse = Xserv.MIDPWM;  
////	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_Low;
////	TIM_OC1Init(TIM1, &TIM_OCInitStructure);
////	
////	
////	TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2;
////	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable;
////	TIM_OCInitStructure.TIM_Pulse = Yserv.MIDPWM;  
////	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_Low;
////	TIM_OC2Init(TIM1, &TIM_OCInitStructure);

//	TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM1; //选择定时器模式:TIM脉冲宽度调制模式2
// 	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出使能
//	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
//	TIM_OCInitStructure.TIM_Pulse=0;

//	TIM_OC1Init(TIM1, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM2 OC1
//	TIM_OC2Init(TIM1, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM2 OC2


//	TIM_ITConfig(TIM1,TIM_IT_Update,ENABLE);
//	
//	
//	TIM_OC1PreloadConfig(TIM1, TIM_OCPreload_Enable);  //使能TIM2在CCR1上的预装载寄存器
//	TIM_OC2PreloadConfig(TIM1, TIM_OCPreload_Enable);  //使能TIM2在CCR2上的预装载寄存器
// 
// 
// 
//	NVIC_InitTypeDef NVIC_InitStructure;


//	NVIC_InitStructure.NVIC_IRQChannel = TIM1_UP_IRQn;  //TIM1中断
//	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;  //先占优先级0级
//	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;  //从优先级3级
//	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE; //IRQ通道被使能
//	NVIC_Init(&NVIC_InitStructure);  //初始化NVIC寄存器
//	
////  TIM_CtrlPWMOutputs(TIM1,ENABLE);	//MOE 主输出使能		
//	TIM_ARRPreloadConfig(TIM1, ENABLE); //使能TIMx在ARR上的预装载寄存器
//	
//	TIM_Cmd(TIM1, ENABLE);  //使能TIM2
//		

//}

void TIM1_UP_IRQHandler(void)
{
    /* Inactive in this variant. Never generate PWM with delays in an ISR. */
    TIM_ClearITPendingBit(TIM1, TIM_IT_Update);
}
void Servo_GPIO_Init(void)
{		
	/*定义一个GPIO_InitTypeDef类型的结构体*/
	GPIO_InitTypeDef GPIO_InitStructure;

//	PWR_BackupAccessCmd(ENABLE);//允许修改RTC 和后备寄存器
//	RCC_LSEConfig(RCC_LSE_OFF);//关闭外部低速外部时钟信号功能 后，PC13 PC14 PC15 才可以当普通IO用。
//	BKP_TamperPinCmd(DISABLE);//关闭入侵检测功能，也就是 PC13，也可以当普通IO 使用
//	PWR_BackupAccessCmd(DISABLE);//禁止修改后备寄存器
//	
	
	
#ifdef USE_SERVO_J1
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J1_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J1_PIN;	
	/*设置引脚模式为通用推挽输出*/
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;  
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J1_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J2
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J2_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J2_PIN;	
	/*设置引脚模式为通用推挽输出*/
 GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J2_PORT*/
  	GPIO_Init(Servo_J2_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J3
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J3_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J3_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz; 
	/*调用库函数，初始化Servo_J3_PORT*/
  	GPIO_Init(Servo_J3_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J4
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J4_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J4_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J4_PORT*/
  	GPIO_Init(Servo_J4_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J5
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J5_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J5_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J5_PORT*/
  	GPIO_Init(Servo_J5_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J6
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J6_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J6_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J6_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J7
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J7_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J7_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J7_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J8
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J8_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J8_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J8_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J9
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J9_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J9_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J9_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J10
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J10_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J10_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J10_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J11
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J11_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J11_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J11_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J12
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J12_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J12_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J12_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J13
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J13_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J13_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J13_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J14
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J14_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J14_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J14_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J15
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J15_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J15_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J15_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J16
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J16_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J16_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J16_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J17
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J17_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J17_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J17_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J18
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J18_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J18_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J18_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J19
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J19_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J19_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J19_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J20
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J20_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J20_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J20_PORT, &GPIO_InitStructure);		  
#endif
 
#ifdef USE_SERVO_J21
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J21_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J21_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J21_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J22
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J22_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J22_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J22_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J23
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J23_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J23_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J23_PORT, &GPIO_InitStructure);		  
#endif

#ifdef USE_SERVO_J24
	/*开启外设时钟*/
	RCC_APB2PeriphClockCmd(Servo_J24_RCC, ENABLE); 
	/*选择要控制的引脚*/															   
  	GPIO_InitStructure.GPIO_Pin = Servo_J24_PIN;	
	/*设置引脚模式为通用推挽输出*/
  	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;   
	/*设置引脚速率为50MHz */   
  	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz; 
	/*调用库函数，初始化Servo_J1_PORT*/
  	GPIO_Init(Servo_J24_PORT, &GPIO_InitStructure);		  
#endif
}

