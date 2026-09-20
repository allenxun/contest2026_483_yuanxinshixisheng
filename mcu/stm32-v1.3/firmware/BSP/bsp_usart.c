#include "AllHeader.h"
#include "bsp_usart.h"
#include "bsp.h"
#include "led.h"
RingBuff_t Uart2_RingBuff,Uart1_RingBuff,Uart3_RingBuff;//????ringBuff????

//USART1 ---- 与PC通信，输出调试信息
void USART1_init(u32 baudrate)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure; 
	
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1 | RCC_APB2Periph_GPIOA, ENABLE);
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOA, &GPIO_InitStructure);    

	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
	GPIO_Init(GPIOA, &GPIO_InitStructure);
	  
	USART_InitStructure.USART_BaudRate = baudrate;
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;
	USART_InitStructure.USART_StopBits = USART_StopBits_1;
	USART_InitStructure.USART_Parity = USART_Parity_No ;
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;
	USART_Init(USART1, &USART_InitStructure); 
	USART_ITConfig(USART1, USART_IT_TXE, DISABLE);

	USART_ITConfig(USART1, USART_IT_RXNE, ENABLE); //开启接收中断       
	USART_ClearFlag(USART1,USART_FLAG_TC);
	USART_Cmd(USART1, ENABLE);
	
	
	NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
	NVIC_Init(&NVIC_InitStructure);
	
//	    RingBuff_Init(&Uart1_RingBuff);

}

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

/**
 * @Brief: UART1发送数据
 * @Note: 
 * @Parm: ch:待发送的数据 
 * @Retval: 
 */
void USART1_Send_U8(uint8_t ch)
{
	while (USART_GetFlagStatus(USART1, USART_FLAG_TXE) == RESET)
		;
	USART_SendData(USART1, ch);
}

/**
 * @Brief: UART1发送数据
 * @Note: 
 * @Parm: BufferPtr:待发送的数据  Length:数据长度
 * @Retval: 
 */
void USART1_Send_ArrayU8(uint8_t *BufferPtr, uint16_t Length)
{
	while (Length--)
	{
		USART1_Send_U8(*BufferPtr);
		BufferPtr++;
	}
}

//串口中断服务函数
void USART1_IRQHandler(void)
{
	uint8_t Rx1_Temp = 0;
	if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET)
	{
		Rx1_Temp = USART_ReceiveData(USART1);
		USART1_Send_U8(Rx1_Temp);
	}
}

///重定向c库函数printf到串口，重定向后可使用printf函数
int fputc(int ch, FILE *f)
{
	/* 发送一个字节数据到串口 */
	USART_SendData(DEBUG_USARTx, (uint8_t)ch);

	/* 等待发送完毕 */
	while (USART_GetFlagStatus(DEBUG_USARTx, USART_FLAG_TXE) == RESET)
		;
	return (ch);
}

///重定向c库函数scanf到串口，重写向后可使用scanf、getchar等函数
int fgetc(FILE *f)
{
	/* 等待串口输入数据 */
	while (USART_GetFlagStatus(DEBUG_USARTx, USART_FLAG_RXNE) == RESET)
		;
	return (int)USART_ReceiveData(DEBUG_USARTx);
}






//USART3
void USART3_Init(uint32_t baudrate)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;

	// 打开串口GPIO的时钟
	RingBuff_Init(&Uart3_RingBuff);
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC | RCC_APB2Periph_AFIO, ENABLE);

	// 打开串口外设的时钟
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART3, ENABLE);
	GPIO_PinRemapConfig(GPIO_PartialRemap_USART3, ENABLE);

	// 将USART Tx的GPIO配置为推挽复用模式
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOC, &GPIO_InitStructure);

	// 将USART Rx的GPIO配置为浮空输入模式
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_11;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
	GPIO_Init(GPIOC, &GPIO_InitStructure);

	//Usart NVIC 配置
	NVIC_InitStructure.NVIC_IRQChannel = USART3_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0; //抢占优先级0
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;		  //子优先级1
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			  //IRQ通道使能
	NVIC_Init(&NVIC_InitStructure);							  //根据指定的参数初始化VIC寄存器

	// 配置串口的工作参数
	// 配置波特率
	USART_InitStructure.USART_BaudRate = baudrate;
	// 配置 针数据字长
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;
	// 配置停止位
	USART_InitStructure.USART_StopBits = USART_StopBits_1;
	// 配置校验位
	USART_InitStructure.USART_Parity = USART_Parity_No;
	// 配置硬件流控制
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
	// 配置工作模式，收发一起
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;
	// 完成串口的初始化配置
	USART_Init(USART3, &USART_InitStructure);
	USART_ITConfig(USART3, USART_IT_IDLE, ENABLE);//开启串口空闲中断  
	// 开启串口接受中断
	USART_ITConfig(USART3, USART_IT_RXNE, ENABLE);  

	// 使能串口
	USART_Cmd(USART3, ENABLE);

   

}

void usart_send(USART_TypeDef* USARTx, uint8_t*data, uint8_t len)
{
	uint8_t i;
	for(i=0;i<len;i++)
	{
		while(USART_GetFlagStatus(USARTx,USART_FLAG_TC)==RESET); 
		USART_SendData(USARTx,data[i]);
	}
}
//发送一个字符
void USART3_Send_U8(uint8_t ch)
{
	while (USART_GetFlagStatus(USART3, USART_FLAG_TXE) == RESET)
		;
	USART_SendData(USART3, ch);
}

//发送一个字符串
/**
 * @Brief: UsART3发送数据
 * @Note: 
 * @Parm: BufferPtr:待发送的数据  Length:数据长度
 * @Retval: 
 */





uint8_t DataDecode(RingBuff_t *ringbuff, uint8_t *data1, uint8_t *data2, uint8_t *data3)      
{
	static uint8_t uart_dec_count;
	static uint8_t uart_rec_data[6];
	uint8_t ret = 1;

	if(Read_RingBuff(ringbuff, &uart_rec_data[uart_dec_count]) == RINGBUFF_ERR){
		return 1;
	 
	}
		if((uart_dec_count == 0)&&(uart_rec_data[uart_dec_count] != 0x55)) {    		//检测第一个数据是否为0x55
		uart_rec_data[uart_dec_count] = 0;						
	}
		else if((uart_dec_count == 1)&&(uart_rec_data[uart_dec_count] != 0xaa)){      //检测第二个数据是否为0xaa
		uart_rec_data[uart_dec_count] = 0;
		uart_rec_data[uart_dec_count-1] = 0;
		uart_dec_count = 0;
		}else if((uart_dec_count == 5)&&(uart_rec_data[uart_dec_count] != 0xfa)){      //检测尾帧是否为0xfa
		uart_rec_data[uart_dec_count] = 0;
		uart_rec_data[uart_dec_count-1] = 0;
		uart_rec_data[uart_dec_count-2] = 0;
		uart_rec_data[uart_dec_count-3] = 0;
		uart_rec_data[uart_dec_count-4] = 0;
		uart_dec_count = 0;
	}
	else{
		if(uart_dec_count == 5)//成功接受一帧数据
		{
			*data1 = uart_rec_data[2];
			*data2 = uart_rec_data[3];
      *data3 = uart_rec_data[4];

			ret = 0;

		}
		uart_dec_count++;
		if(uart_dec_count == 6)
		{
			uart_dec_count = 0;
		}
//	
	}
	return ret;	

} 

uint8_t DataDecode2(RingBuff_t *ringbuff, uint8_t *data1)      
{
	static uint8_t uart_dec_count;
	static uint8_t uart_rec_data[4];
	uint8_t ret = 1;

	if(Read_RingBuff(ringbuff, &uart_rec_data[uart_dec_count]) == RINGBUFF_ERR){
		return 1;
	 
	}
		if((uart_dec_count == 0)&&(uart_rec_data[uart_dec_count] != 0x55)) {    		//检测第一个数据是否为0x55
		uart_rec_data[uart_dec_count] = 0;						
	}
		else if((uart_dec_count == 1)&&(uart_rec_data[uart_dec_count] != 0xaa)){      //检测第二个数据是否为0xaa
		uart_rec_data[uart_dec_count] = 0;
		uart_rec_data[uart_dec_count-1] = 0;
		uart_dec_count = 0;
		}else if((uart_dec_count == 3)&&(uart_rec_data[uart_dec_count] != 0xfa)){      //检测尾帧是否为0xfa
		uart_rec_data[uart_dec_count] = 0;
		uart_rec_data[uart_dec_count-1] = 0;
		uart_rec_data[uart_dec_count-2] = 0;

		uart_dec_count = 0;
	}
	else{
		if(uart_dec_count == 3)//成功接受一帧数据
		{
			*data1 = uart_rec_data[2];
	

			ret = 0;

		}
		uart_dec_count++;
		if(uart_dec_count == 4)
		{
			uart_dec_count = 0;
		}
//	
	}
	return ret;	

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






//串口中断服务函数
void USART3_IRQHandler(void)
{
	uint8_t rdata ,data1,data2,data3;
	if(USART_GetITStatus(USART3, USART_IT_RXNE) != RESET)
	{	
		rdata = USART_ReceiveData(USART3);
		if(Write_RingBuff(&Uart3_RingBuff, rdata) == RINGBUFF_ERR){//缓冲区满灯亮
			LED1=0;
		}else{
			LED1=1;
		}
	}else if(USART_GetITStatus(USART3, USART_IT_IDLE) != RESET){//空闲帧中断
        rdata = USART_ReceiveData(USART3);
//			DataDecode(&Uart3_RingBuff, &data1, &data2, &data3);
		

	
//				
				

	}
}


//UART5
void UART5_init(u32 baudrate)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure; 
	
	
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_UART5, ENABLE);
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC | RCC_APB2Periph_GPIOD , ENABLE);
	
	
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_12;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOC, &GPIO_InitStructure);    

	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_2;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
	GPIO_Init(GPIOD, &GPIO_InitStructure);
	  
	USART_InitStructure.USART_BaudRate = baudrate;
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;
	USART_InitStructure.USART_StopBits = USART_StopBits_1;
	USART_InitStructure.USART_Parity = USART_Parity_No ;
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;
	USART_Init(UART5, &USART_InitStructure); 
	USART_ITConfig(UART5, USART_IT_TXE, DISABLE);  
	USART_ITConfig(UART5, USART_IT_RXNE, ENABLE); //开启接收中断       
	//USART_ClearFlag(UART5,USART_FLAG_TC);
	USART_Cmd(UART5, ENABLE);
	
	
	NVIC_InitStructure.NVIC_IRQChannel = UART5_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 1;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 4;
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
	NVIC_Init(&NVIC_InitStructure);

}


//发送一个字符
void UART5_Send_U8(uint8_t ch)
{
	while (USART_GetFlagStatus(UART5, USART_FLAG_TXE) == RESET)
		;
	USART_SendData(UART5, ch);
}

//发送一个字符串
/**
 * @Brief: UsART3发送数据
 * @Note: 
 * @Parm: BufferPtr:待发送的数据  Length:数据长度
 * @Retval: 
 */
void UART5_Send_ArrayU8(uint8_t *BufferPtr, uint16_t Length)
{
	while (Length--)
	{
		UART5_Send_U8(*BufferPtr);
		BufferPtr++;
	}
}

//串口中断服务函数
void UART5_IRQHandler(void)
{
	uint8_t Rx5_Temp;
	if (USART_GetITStatus(UART5, USART_IT_RXNE) != RESET)
	{
		Rx5_Temp = USART_ReceiveData(UART5);
//		UART5_Send_U8(Rx5_Temp);
		deal_bluetooth(Rx5_Temp);
	}
}

int8_t receiveJson(RingBuff_t *ringbuff, char *str)
{
	static uint8_t reading,j;
	uint8_t readbuff,ok = 0;
	if(Read_RingBuff(&Uart1_RingBuff,&readbuff) == RINGBUFF_OK){
		if(readbuff == '{'){
			reading = 1;
			str[j++] = readbuff;
			ok = 0;
		}else if(readbuff == '}' && reading == 1){
			reading = 0;
			str[j++] = readbuff;  
			str[j++] = '\0';
			ok = 1;
		}else if(reading == 1){
			str[j++] = readbuff;
		}else {
			j = 0;
			reading = 0;
			ok = 0;
		}
	}
	return ok;
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
