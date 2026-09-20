# 板载音频只读前置诊断

`k7audio preflight` 只读取8个固定CRU/IOC地址，共两份快照。不会访问I2C3或SAI1寄存器，不改时钟/引脚，不向codec发事务，不播放或录音。需要当前BSP已存在的CRU/IOC Device映射。命令result=0只说明快照完成，不代表codec可用。

CLKSEL57[5:4]顺序：clk_gpll_div6、clk_cpll_div10、clk_cpll_div20、xin24m。前三项是可选父PLL及可编程分频的composite，不能按名字断言200/100/50MHz；输出parent/divisor与实际频率未知标志。CLKSEL55[3:2]是PCLK_BUS_ROOT父选择，值3未定义；GATE位1表示关闭。

来源：`evidence/audio-sdk-extra-20260910/kernel-6.1/drivers/clk/rockchip/clk-rk3576.c` 的CLKSEL0/1/55/57、GATE0/11/12，以及同快照pinctrl-rockchip.c的GPIO4B4/B5 mux；候选审查见parallel-cxx-unwind-medium/audio-clock-preflight-v1。实际PLL频率、复位、供电、上拉、I2C时序及codec事务仍是下一层门槛。
