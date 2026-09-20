#ifndef __BSP_USART_H
#define __BSP_USART_H

#include "AllHeader.h"
#define EN_USART1_RX 			1		//??(1)/??(0)??1??
	  	
#define  RINGBUFF_LEN          (500)     //?????????
#define  RINGBUFF_OK           1     
#define  RINGBUFF_ERR          0   

typedef struct
{
    volatile uint16_t Head;           
    volatile uint16_t Tail;
    volatile uint16_t Lenght;
    uint8_t  Ring_data[RINGBUFF_LEN];
}RingBuff_t;


extern RingBuff_t Uart2_RingBuff,Uart1_RingBuff,Uart3_RingBuff;

uint8_t DataDecode(RingBuff_t *ringbuff, uint8_t *data1, uint8_t *data2, uint8_t *data3);
uint8_t Write_RingBuff(RingBuff_t *ringbuff, uint8_t data);
uint8_t Read_RingBuff(RingBuff_t *ringbuff, uint8_t *rData);


void RingBuff_Init(RingBuff_t *ringbuff);
uint8_t DataDecode2(RingBuff_t *ringbuff, uint8_t *data1)  ;
uint8_t DataDecode1(RingBuff_t *ringbuff, uint8_t *data1, uint8_t *data2, uint8_t *data3,uint8_t *data4);
void USART1_init(u32 baudrate);
void USART1_Send_ArrayU8(uint8_t *BufferPtr, uint16_t Length);
void USART1_Send_U8(uint8_t ch);
void usart_send(USART_TypeDef* USARTx, uint8_t*data, uint8_t len);
int8_t receiveJson(RingBuff_t *ringbuff, char *str);

void USART3_Init(uint32_t baudrate);
void USART3_Send_ArrayU8(uint8_t *BufferPtr, uint16_t Length);
void USART3_Send_U8(uint8_t ch);

void UART5_init(u32 baudrate);
void UART5_Send_U8(uint8_t ch);
void UART5_Send_ArrayU8(uint8_t *BufferPtr, uint16_t Length);

#endif
