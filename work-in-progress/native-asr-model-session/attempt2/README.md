# 第二轮真实 decoder 会话验收

已通过ARM64编译、固件链接、ELF审计、单次OTG RAM传输及板端Session创建/释放。分配峰值141998120字节，389条记录，失败0，释放后0。旧记录上限128不足，当前2048。详见acceptance.json与probe日志。

这只是decoder会话创建，不包含decoder推理、encoder、ASR识别或配网。下一步接encoder和真实音频输入；模型持久存储仍未集成。Wi-Fi/BLE当前未启动。本轮未刷eMMC或操作执行机构。
