#include "AllHeader.h"

#define RX_LEN 10

char rxbuff[RX_LEN];//一包数据的存储量
u8 recv_i = 0;
u8 rx_flag = 0;//有效数据包的位置
u8 newdata_flag = 0;//完成一包数据接收的标志

//接收蓝牙的信息并做处理  //$A090#  :第一路的舵机90度
void deal_bluetooth(u8 Rx_temp)  //把尾（#）去掉
{
		if(Rx_temp == '$')
	{
		rx_flag = 1;
	}
	if(Rx_temp == '#')
	{
		rxbuff[recv_i] = '\0';
		recv_i = 0;
		rx_flag = 0;
		deal_data();
		memset(rxbuff,0,RX_LEN);
	}
	if(rx_flag == 1 )
	{
		rxbuff[recv_i] = Rx_temp;
		recv_i ++;
	}

}

//处理包的数据
u8 deal_data(void) //传过来的是字符类型
{
	u8 duo_num = 0;
	u8 Hor,column;
	u16 angle = 0;
	duo_num = rxbuff[1] - 64; 
	Hor = (duo_num-1)/8;//得到组别 0.1.2     -1:数组是从0开始
	column=(duo_num-1)%8; //一组里的对应的舵机位置
	
	angle = (rxbuff[2]-48)*100 + (rxbuff[3]-48)*10 + rxbuff[4]-48;
	
	if(angle <= 0)
	{
		angle = 0;
	}
	if(angle >= 270)
	{
		angle = 270;
	}
	
	Angle_J[Hor][column] = angle;	
	
	return 0;
}

