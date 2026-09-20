# 独立MCLKOUT门控漏项与最小补丁

确认当前platform仅配置CRU clock与GPIO4_A2 mux，遗漏 `mclkout_sai1` 的独立to-IO门控。它不是选择另一频率源的mux：rk3576.dtsi:153节点地址0x26046400、parent CLK_SAI1_MCLKOUT、shift1、bit-set-to-disable、PD_AUDIO；精确冻结clk-out.c显式CLK_GATE_HIWORD_MASK，按属性追加CLK_GATE_SET_TO_DISABLE，clk_hw_register_gate以该shift/parent注册，并对provider dev启用runtime PM。因此clear bit1是有源码依据的启用方式，写0x00020000；不能读改写整32位覆盖其他SAI输出。

独立mclkout.patch基于input/platform.c/h，只添加mclkout_before/mclkout_after字段与少量操作。不扩old[]，不与A的pull_none old[10]索引占用冲突；root应按差异合并，不用本目录整文件覆盖A补丁。

setup在AUDIO repair/ACK/IDLE全部确认后，第一次读取IOC+0x6400保存完整mclkout_before；CRU配置完成后hiword clear bit1，读完整mclkout_after并要求bit1为0，然后才继续VERSION读取。setup不启动SAI流。必须只在AUDIO域已上电后访问这个寄存器，不能移到开头snapshot循环。root日志打印before/after完整hex，以区分实际漏gate关闭与原来已开；只有before.bit1=1才证明本次修复确实改变了输出门控状态。

cleanup沿用原ready/quiescent门禁，先以hiword将bit1置1暂时断开to-IO输出，再恢复原clock/pin字段，最后只恢复保存的bit1并读回。其他bit不受写掩码影响；整raw仅诊断不整值回写。AUDIO保持供电，失败held不自动重试。若setup中途失败ready=0，仍采用原监督恢复约束；没有新建冒险cleanup捷径。codec/amp先真实停机仍由root/B保证。

## 4.096MHz/16kHz边界

冻结官方es8323.c coeff_div:393明确包含 `{4096000,16000,256,0x2,0x0}`；supported_mclk_lrck_ratios包含256，hw_params验证4.096M/256=16k再写ADC/DAC采样系数。因此该频率组合有明确官方支持，不应因录音全零就改到另一猜测MCLK。S32_LE会设置ADC interface0x10/DAC0x20（保留格式位），与B profile来源一致。ES8388硬件通过DTS everest,es8323兼容驱动，不在此把兼容表扩大为所有ES8388修订/模拟通路的实测保证。

CRU链独立核对：24MHz经frac0 64/375=4.096MHz；CLKSEL13 parent index3、CLKSEL46 source index1/div1、最终内部MCLK；CRU CLK_SAI1_MCLKOUT gate9bit13→本次IO gatebit1→GPIO4_A2 mux1→codec MCLK。SAI CKR div4得到1.024MHz BCLK，64bit帧16k。寄存器数值正确不等于电气波形存在，输出gate缺失正是两者之间的独立条件。听到tone不单独排除codec残余/其他时钟源状态，必须看before/after与真实capture。

## 验证

本目录python run.py，真实MinGW GCC O0/O2 C11 Wall/Wextra/Werror/pedantic编译运行通过。测试模拟初值0xa7，启用后0xa5、清理后0xa7，确认只bit1变化；power timeout不访问IO gate/SAI；gate写不生效时读回报-5、held且不读SAI VERSION。原始输出test-output.txt，所有精确来源（包括clk-out提取记录）、候选与补丁哈希inputs/outputs.json。

没有设备/SDK/正式源码操作，没有新ARM构建或声学结果。已确认“正式平台缺少此gate控制”，尚未确认“本板全零唯一由gate导致”；后者等root下一镜像before/after及录音证据。
