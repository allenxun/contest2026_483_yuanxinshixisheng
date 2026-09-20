/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         bsp_servo.c	
* @version      V1.0
* @brief        6�������������Դ�ļ�
* @details      
* @par History  ������˵��
*                 
* 
*/

#include "bsp_servo.h"
#include "delay.h"



ServTypdef Xserv = {
    .pwm = 1492,
	.MAXPWM = 2500,
	.MINPWM = 500,
	.MIDPWM = 1492 /* Midpoint of selected X endpoints: (2452 + 532) / 2. */
};

/* y???? - */
ServTypdef Yserv = {
    .pwm = 750,
	.MAXPWM = 2300,
	.MINPWM = 500,
	.MIDPWM = 700//750�м��
};//׷��


static uint16_t servo_limit(const ServTypdef *servo, int offset)
{
    int32_t pulse = (int32_t)servo->MIDPWM + offset;
    if (pulse > servo->MAXPWM) pulse = servo->MAXPWM;
    if (pulse < servo->MINPWM) pulse = servo->MINPWM;
    return (uint16_t)pulse;
}

void Servo_PWM_Init(void)
{
    GPIO_InitTypeDef gpio;
    TIM_TimeBaseInitTypeDef timer;
    TIM_OCInitTypeDef oc;
    RCC_ClocksTypeDef clocks;
    uint32_t timer_hz;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);
    GPIO_PinRemapConfig(GPIO_FullRemap_TIM2, DISABLE);
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin = GPIO_Pin_0 | GPIO_Pin_1;
    gpio.GPIO_Mode = GPIO_Mode_AF_PP;
    gpio.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &gpio);
    RCC_GetClocksFreq(&clocks);
    timer_hz = clocks.PCLK1_Frequency;
    if (clocks.PCLK1_Frequency != clocks.HCLK_Frequency) timer_hz *= 2;
    TIM_DeInit(TIM2);
    TIM_TimeBaseStructInit(&timer);
    timer.TIM_Prescaler = (uint16_t)(timer_hz / 1000000UL - 1);
    timer.TIM_Period = 19999; /* 1 us ticks, 50 Hz; verify servo specification. */
    TIM_TimeBaseInit(TIM2, &timer);
    TIM_OCStructInit(&oc);
    oc.TIM_OCMode = TIM_OCMode_PWM1;
    oc.TIM_OutputState = TIM_OutputState_Enable;
    oc.TIM_OCPolarity = TIM_OCPolarity_High;
    oc.TIM_Pulse = Xserv.MIDPWM;
    TIM_OC1Init(TIM2, &oc);
    oc.TIM_Pulse = Yserv.MIDPWM;
    TIM_OC2Init(TIM2, &oc);
    TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);
    TIM_OC2PreloadConfig(TIM2, TIM_OCPreload_Enable);
    TIM_ARRPreloadConfig(TIM2, ENABLE);
    TIM_GenerateEvent(TIM2, TIM_EventSource_Update);
    TIM_ClearFlag(TIM2, TIM_FLAG_Update);
    Xserv.pwm = Xserv.MIDPWM;
    Yserv.pwm = Yserv.MIDPWM;
    TIM_Cmd(TIM2, ENABLE);
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

void servo_ctr(ServTypdef *servo, int offset)
{
    uint16_t pulse = servo_limit(servo, offset);
    if (servo == &Xserv) TIM_SetCompare1(TIM2, pulse);
    else if (servo == &Yserv) TIM_SetCompare2(TIM2, pulse);
    servo->pwm = pulse;
}

int Angle_J[GROUP_NUM][DUOJI_NUM];

/**
* Function       Servo_J1
* @author        
* @date          
* @brief         ���1���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J1(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J1_PORT, Servo_J1_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J1_PORT, Servo_J1_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J2
* @author        
* @date            
* @brief         ���2���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J2(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J2_PORT, Servo_J2_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J2_PORT, Servo_J2_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J3
* @author        
* @date          
* @brief         ���3���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J3(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J3_PORT, Servo_J3_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J3_PORT, Servo_J3_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J4
* @author        
* @date              
* @brief         ���4���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J4(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J4_PORT, Servo_J4_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J4_PORT, Servo_J4_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J5
* @author        
* @date             
* @brief         ���5���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J5(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J5_PORT, Servo_J5_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J5_PORT, Servo_J5_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J6
* @author        
* @date             
* @brief         ���6���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J6(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J6_PORT, Servo_J6_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J6_PORT, Servo_J6_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J7
* @author        
* @date             
* @brief         ���7���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J7(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J7_PORT, Servo_J7_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J7_PORT, Servo_J7_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       Servo_J8
* @author        
* @date             
* @brief         ���8���ƺ���
* @param[in]     v_iAngle �Ƕȣ�0~180��
* @param[out]    void
* @retval        void
* @par History   ��
*/
void Servo_J8(int v_iAngle)/*����һ�����庯��������ģ�ⷽʽ����PWMֵ*/
{
	int pulsewidth;    						//������������

	pulsewidth = (v_iAngle * 11) + 500;			//���Ƕ�ת��Ϊ500-2480 ������ֵ

	GPIO_SetBits(Servo_J8_PORT, Servo_J8_PIN );		//������ӿڵ�ƽ�ø�
	delay_us(pulsewidth);					//��ʱ����ֵ��΢����

	GPIO_ResetBits(Servo_J8_PORT, Servo_J8_PIN );	//������ӿڵ�ƽ�õ�
	delay_ms(20 - pulsewidth/1000);			//��ʱ������ʣ��ʱ��
}

/**
* Function       front_detection
* @author        
* @date             
* @brief         ��̨�����ǰ
* @param[in]     void
* @param[out]    void
* @retval        void
* @par History   ��
*/
void front_detection()
{
	int i = 0;
  	//�˴�ѭ���������٣�Ϊ������С�������ϰ���ķ�Ӧ�ٶ�
  	for(i=0; i <= 15; i++) 						//����PWM��������Ч��ʱ�Ա�֤��ת����Ӧ�Ƕ�
  	{
    	Servo_J1(90);						//ģ�����PWM
  	}
}

/**
* Function       left_detection
* @author        
* @date             
* @brief         ��̨�������
* @param[in]     void
* @param[out]    void
* @retval        void
* @par History   ��
*/
void left_detection()
{
	int i = 0;
	for(i = 0; i <= 15; i++) 						//����PWM��������Ч��ʱ�Ա�֤��ת����Ӧ�Ƕ�
	{
		Servo_J1(175);					//ģ�����PWM
	}
}

/**
* Function       right_detection
* @author        
* @date             
* @brief         ��̨�������
* @param[in]     void
* @param[out]    void
* @retval        void
* @par History   ��
*/
void right_detection()
{
	int i = 0;
	for(i = 0; i <= 15; i++) 						//����PWM��������Ч��ʱ�Ա�֤��ת����Ӧ�Ƕ�
	{
		Servo_J1(5);						//ģ�����PWM
	}
}

