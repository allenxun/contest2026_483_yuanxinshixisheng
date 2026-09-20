# parallel-voice-provision-contract-sol

纯主机可测的“板端规则语音配网”协议与状态机候选。所有端口均为抽象接口，测试只用公开虚拟数据，不接触设备、SDK、无线、ASR/TTS 引擎或真实凭据。

在本目录执行：

```powershell
g++ -std=c++17 -Wall -Wextra -Werror -Iinclude src/voice_provision_contract.cpp tests/test_contract.cpp -o test_contract.exe
./test_contract.exe
```
