# 真实模型与配置核对

选定原路径在 `E:/openvela/语音模块/openvela-voicelink/models/` 下，不复制模型。完整选定文件大小、SHA-256、ONNX输入输出/metadata见 evidence/models.json；inspect_models.py 用 ONNX 1.17.0 读取结构，没有用它代替推理引擎。

| 模型 | 字节 | SHA-256 |
| --- | ---: | --- |
| sherpa-onnx-streaming-paraformer-bilingual-zh-en/encoder.int8.onnx | 165462184 | 81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a |
| 同目录 decoder.int8.onnx | 71664561 | f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f |
| vits-icefall-zh-aishell3/model.onnx | 30482262 | 5511d651b7840c0a93a6bbfd4afd070a2c7f39ca1ec3ff2ecd73191519bbb852 |

ASR encoder metadata明确 model_type=paraformer、vocab_size=8404、lfr_window_size=7、lfr_window_shift=6、encoder_output_size=512、decoder_num_blocks=16、decoder_kernel_size=11。输入speech为float [batch,frames,560]、speech_lengths为int32；输出enc [batch,frames,512]、enc_len与alphas。decoder输入enc/enc_len、acoustic_embeds/acoustic_embeds_len和16组float [batch,512,10] cache；输出logits末维8404、sample_ids和16组cache。tokens.txt有8404行。结构与流式Paraformer接口一致，并且真实加载/推理已验证；不只依赖目录名。encoder/decoder原始float版本没有选用或复制。

实际配置：OnlineRecognizer的paraformer.encoder/decoder指向INT8文件，tokens指向同目录词表，feat_config.sample_rate=16000、feature_dim=80、greedy_search、cpu、num_threads=1。560是7帧LFR后的模型特征维度，不能把feature_dim错误设为560。候选binding用512样本批次feed，InputFinished后drain，未额外填尾部静音；识别文本存在不准确及尾句不完整，不作为准确率验收。

TTS metadata为vits、Chinese、n_speakers=174、**sample_rate=8000**。输入tokens/int64 [N,T]、tokens_lens/int64 [N]、noise_scale/alpha/noise_scale_dur各float[1]、speaker/int64[N]，输出audio为float[N,T]。实际使用model/tokens/lexicon与现有rule.far，rule_fars位于TTS config顶层；sid=0，speed=1，length_scale=1、noise_scale=.667、noise_scale_w=.8、silence_scale=1、max_num_sentences=1、CPU单线程。不能假设TTS输出为16k；生成WAV已核实8kHz、单声道、PCM16。选定辅助文本/FST/FAR/说话人表均只读记录哈希；此次仅rule.far参与规则配置，独立fst文件未逐一执行。

模型来源说明：ASR原README给出ModelScope damo转换来源与Hugging Face metadata脚本。本轮测试音频取原包test_wavs/0.wav（16000Hz单声道PCM16，160850帧，10.053125秒），记录了实际文件哈希；没有重新下载/独立认证该WAV的发布来源。TTS测试文本为本轮自定“你好，欢迎使用语音助手。”；噪声采样导致多次合成长度/字节可能不同，交付WAV哈希只标识该次真实产物，不承诺逐比特复现。

真实运行库来自[官方 v1.12.14 release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.12.14)，资产名 sherpa-onnx-v1.12.14-win-x64-shared.tar.bz2，下载SHA-256 `78fa331bac4d20828a867b14283950727ce668fe751d1a792352b7e035b0ffe1`。sherpa自报1.12.14/26aa2fa9；调用该包onnxruntime.dll的OrtGetApiBase/GetVersionString得到 **ONNX Runtime 1.17.1**，不是结构检查包ONNX 1.17.0。DLL与头文件哈希见evidence/delivery.json。没有切换其他sherpa版本。
