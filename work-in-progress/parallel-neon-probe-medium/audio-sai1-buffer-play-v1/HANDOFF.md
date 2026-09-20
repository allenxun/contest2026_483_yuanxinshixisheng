# 最小只读PCM32缓冲播放接口

基于冻结audio-sai1-pio-v3，新增 `pio_play_buffer(port,prepared,mclk,source,source_words,frames,result)`。source为const uint32_t交错左右声道原始字；frames1..48000，source_words>=2*frames，最大3秒/96000word/384000字节。先检查frames上限才计算2*frames，UINT_MAX输入拒绝，无乘法溢出。已有pio_run接口、tone幅度与8..3200帧限制保持；内部复用同一run实现，不新增broker或线程。

每次TXDR取source相应下标，左右样本独立，完全按位发送，不合成、不补零、不做音量归一/重采样/格式转换。port.amplitude只限制tone，不对buffer生效；root必须在codec/amp层设置安全音量。不能将source_words容量当实际采集帧数，必须传成功采集的result.frames；录音是否真实有效由root证据决定，本API不能鉴别来源。禁止把主机测试向量冒充录音。

调用者在调用期间持有source所有权且保持不变；source不得与port/result可写存储重叠，不在中断或另一任务修改。接口不保留返回后的指针、不分配内存。出现部分TX错误时frames按原逻辑计完整入队帧，不假称已经声学播放；不自动补尾或重试。capture路径原样。

预填数量min(16,2*frames)，短输入1..7帧不额外读8帧或补静音；完整FIFO四字段sum必须等于实际预填word数。>=8帧行为与v3一致。后续每对word取source[2*frames_queued]及下一项；补样阈值、poll预算、时间限制、hooks、TXUI判定、收尾等待与stop均未改变。A正在审查TX末尾竞态，本候选不抢改该逻辑；root合并时应用buffer-play.patch的局部source差异，不用整文件覆盖A修改。

`python run.py`在真实Windows MinGW GCC C11 O0/O2严格警告编译运行通过，原始命令/输出/exit保存test-output.txt。测试逐字核对1/7/8/9/3200/48000帧全部写入；左右测试向量不同并覆盖高位/负数位型；确认source未变、总写次数恰2*frames及FIFO<=16。NULL/短容量/0/48001/UINT_MAX输入均零硬件写拒绝，保留v3全部回归测试。主机数据是明确合成测试向量，不是真机录音。没有SDK、正式文件、设备或其他候选改动。

输入快照/哈希见inputs.json，最小补丁buffer-play.patch，交付哈希outputs.json。没有目标编译/实际回放验收；第一版硬件应继续root既定tone/capture步骤，不被此候选阻塞。
