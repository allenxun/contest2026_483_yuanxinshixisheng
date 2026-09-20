# 流收尾与模型生命周期结论

## 有证据支持的收尾改进

固定sherpa v1.12.14 / commit 26aa2fa93210376a89de3a65a1a4dd320c37f5e9，使用原INT8 Paraformer模型。官方源码按该commit保存于input/，URL/哈希见evidence/official-sources.json。

- `online-recognizer-paraformer-impl.h:157` 的 IsReady 只在已处理帧数加chunk_size小于可用帧时为真；chunk_size_=61。`online-stream.cc` 的InputFinished转交feature extractor，未直接绕过IsReady条件。因此“标记EOF然后drain”不等于任意剩余片段都一定被解码。
- [官方C示例](https://github.com/k2-fsa/sherpa-onnx/blob/26aa2fa93210376a89de3a65a1a4dd320c37f5e9/c-api-examples/decode-file-c-api.c) 在217–226行先补0.3秒尾静音，再InputFinished，再while IsReady解码。官方CLI源码121–133行另有0.3秒前补和0.8秒后补。
- C API声明要求只在IsReady为真时decode，InputFinished之后不再AcceptWaveform；本候选没有破坏这两个约束，没有扩大1024步预算，也没有强行decode未就绪帧。

原test_wavs/0.wav的“期望”取[官方文档发布的模型输出](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-paraformer/paraformer-models.html)：末尾为“星期三”。这是发布的模型参考，**不是已独立核听的自然人声转写真值**；不能据此计算正式WER。实验前expectations.json已记录完整参考和来源，没有测试后改成当前输出。

| 同一人声样例处理 | 实际尾部/差异 | 解码次数/最大单轮 |
| --- | --- | --- |
| 无前补、无后补、512样本批次 | 停在“星期”，参考尾字缺失 | 16 / 1 |
| 无前补、后补300ms、512批次 | 恢复“星期三” | 17 / 1 |
| 无前补、后补800ms/1200ms/2000ms | 均为“星期三”，没有更好的整句识别 | 18/18/20，每轮最大1 |
| 无前补、后补800ms、160批次 | 同512批次 | 18 / 1 |
| 无前补、后补800ms、整段提交 | 同512批次 | 18 / 16 |
| 前补300ms、后补800ms、512批次 | 再次停在“星期”；英文变为“tedis” | 18 / 1 |
| 前补300ms、后补800ms、整段提交 | 同上一行 | 18 / 17 |
| 无前补、后补800ms、endpoint开启但不reset | 同关闭endpoint，19次观察到endpoint | 18 / 1 |

在这一个样例上，尾部缺失可通过有限补尾纠正；额外前补引发的帧对齐变化是另一个独立因素。分块大小和decode预算不是本次尾字差异的解释。不能推广成“所有模型都不要前补”或“300ms足以覆盖所有语音”。没有改动模型内核，跨样例泛化仍未验收。

补尾前后/EOF后文本分别保存在stdout；参考尾字在补尾期间已经出现，InputFinished后的drain没有再次改善该样例。endpoint仅作为状态观测，不在最后一刻reset流；如果先reset再取结果会丢失当前段，正式代码必须先消费结果再开始新段。

无前补、补尾300ms后的实际整句为 `昨天是 monday today day is 礼拜二 the day after tomorrow 是星期三`，不等于官方发布完整参考；自然人声真值未核定，保留英文重复等误差。原自合成WAV期望文本为“你好，欢迎使用语音助手。”，无后补/补800ms都得到 `你也好刚才经使用语音助手`；不将它改为期望，也不当作自然人声准确率。该错误没有被补尾解决。

## 候选补丁

`candidate.patch`只新增显式`finishWithTail(text, stop, sample_rate, tail_ms, budget)`。旧finish行为保持不变；选定Paraformer配置由调用者显式选300ms，本轮不设置万能默认。方法以最多512样本的固定零缓冲分批feed，再调用原finish；支持范围限制为正采样率≤192kHz、tail≤2000ms，每轮decode仍有原预算。取消、预算失败、非法配置均释放流，不允许结束后继续feed。尾静音数量按传入实际采样率计算，8k与16k不可混淆。

真实库候选测试1657条断言通过，含160/512批次的参考尾部、重复EOF、空输入、EOF取消、零预算真实ready失败、非法尾部上限、失败后的流失效。零预算探针退出21、取消探针退出20是预先声明的预期拒绝，不是假装模型成功。空输入结果为空，应用应映射“无识别文本”，不能提交空Agent任务。未实现抢占单次ONNX解码或生成；取消在调用边界生效。

## 内存和加载取舍

四方案各3个独立进程，共12进程；ASR-only、TTS-only、双常驻、ASR执行后销毁再加载TTS。第二轮反序执行以避免全部方案固定顺序偏差；不清系统文件缓存，因此这是进程冷启动/可能热文件缓存数据，不是机器冷启动基准。

每20ms以psutil6.1.1采样子进程private/working_set/OS peak_wset，**逐样本CSV保留**。stdout阶段时间戳记录模型加载、首次非空ASR结果、完整TTS生成、销毁；首次输出不是实时录音首字时延，ASR输入由文件尽快送入，TTS接口为阻塞生成整个音频。父子时钟原点相差进程启动开销，不用于毫秒级阶段归因。每个退出前等待250ms观察释放后的占用，最后五次private中位数约14–17MiB，不代表板端一定同样归还系统。

精确对比表见evidence/memory-table.md，全部运行记录与范围见memory-summary.json。private峰值中位数：仅ASR702.7MiB、仅TTS294.9MiB、双常驻960.9MiB、顺序加载715.9MiB；双常驻范围953.4–978.2MiB，顺序加载691.0–734.7MiB。未把20ms采样峰值等同绝对峰值；OS报告的peak_wset也单独保留。

建议主会话优先验证“ASR处理完整段→结束并销毁stream/result/recognizer→按需加载TTS→生成/播放完成后销毁TTS→需要再听时重建ASR”的半双工方案。此Windows实验把峰值private中位数降低约245MiB，但付出每次ASR加载约2.4–3.0秒、TTS加载约3.0–3.3秒的成本，不能声称交互流畅。可在板端以实际时延预算决定保留ASR、按需TTS，或将ASR/TTS都卸载；保持ASR再加载TTS仍会遇到双常驻峰值，不能把“按需生成”误当成“按需加载”。

若要求随时唤醒和低时延播报，当前全量双模型方案没有足够板端证据，不能单凭Windows约979MiB小于1GiB就批准放入专用池；进程private包含Windows/ORT分配，NuttX分配器、栈、音频DMA/缓冲、模型池是否承接全部分配都未验证。也不因本测量自动换模型/量化版本。本轮生命周期实验使用官方C API独立所有权，并未给旧SpeechSession强行增加单模型模式；正式集成应提供明确ASR/TTS独立生命周期及失败回滚接口后再验收。
