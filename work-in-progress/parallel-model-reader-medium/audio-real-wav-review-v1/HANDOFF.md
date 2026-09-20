# Windows 真实录音可懂度检查入口

本轮仅定位并只读核对现存文件，未执行 ASR、未读取实际人声 WAV、未下载或复制模型。后续由 root 取得真实 capture-high16.wav 后决定执行。Windows 转写只能辅助评估录音可懂度，不是板端 ASR 验收。

## 已有真实入口

- 冻结交接：`work-in-progress/parallel-voicelink-runtime/HANDOFF.md`、`MODELS.md`。
- 已验证命令和返回：`evidence/asr-cli-20260910T032011222176Z/result.json`（相对此 runtime 目录）；退出 0，约 3.274 秒，采样 RSS 550662144 bytes。测试是模型包自带 WAV，并非板载麦克风。
- 实库：`E:/openvela/VelaVision/work-in-progress/parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared/bin/sherpa-onnx.exe`；同级 `../lib/` 包含 DLL。已有交接记录 sherpa 1.12.14、ORT 1.17.1。
- 模型：`E:/openvela/语音模块/openvela-voicelink/models/sherpa-onnx-streaming-paraformer-bilingual-zh-en/`，选 `encoder.int8.onnx`、`decoder.int8.onnx`、`tokens.txt`。本轮确认存在及大小，未重新扫描大模型内容；历史 SHA256 见 models.json，不冒充本轮校验。
- 官方冻结 help 要求单声道 PCM16；保留 16000Hz，CPU/1线程/greedy_search、feature_dim=80。
- 不用 `real_binding.exe`：会同时加载 TTS，且本任务不需要 TTS。不直接调用旧 `scripts/run_measured.py`：它写旧 runtime/evidence，违反冻结目录边界。

## root 后续方法（本轮未执行）

1. 保存真实原 WAV、原始 raw32 和采集命令/固件哈希。确认 high16 转换来自实际样本，不先做自动增益或滤波。
2. 验证 WAV 为未压缩 PCM16、16000Hz、2 声道、非空，读取帧数与头一致。逐通道统计峰值/RMS/非零数/饱和样本数，人工听原音。全零不能用 ASR 幻觉解释为可懂。
3. 左右通道分别导出，不默认平均：差分 MIC 的数字两通道关系必须由样本验证，平均可能抵消。以人耳较清楚声道做主结果，另一通道保留对照；不要只选择“识别得像预期”的文本。
4. 对照用户实际朗读文字，记录漏字/错字及环境。现有交接中识别文本有英语错误和尾句不完整；一次失败也不能独自区分模型局限与音频问题。

以下 Python 片段由 root 放入**新的真实采集证据目录**后执行，INPUT 改为真实路径，OUT 必须是新的目录；只读原 WAV，不覆盖原证据。不使用云、不联网、不重建 ASR。它每路保留 PCM 原数值，无重采样/增益/平均。单文件最长 60 秒以约束内存，进程超时 120 秒；subprocess 超时会终止并等待该直接子进程，不保证杀死潜在子孙进程。

```python
import hashlib, json, math, os, pathlib, struct, subprocess, time, wave
INPUT = pathlib.Path(r'ROOT_SET_REAL_CAPTURE_HIGH16_WAV')
OUT = pathlib.Path(r'ROOT_SET_NEW_EVIDENCE_DIRECTORY')
R = pathlib.Path(r'E:/openvela/VelaVision/work-in-progress/parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared')
M = pathlib.Path(r'E:/openvela/语音模块/openvela-voicelink/models/sherpa-onnx-streaming-paraformer-bilingual-zh-en')
with wave.open(str(INPUT), 'rb') as w:
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (2, 2, 16000, 'NONE')
    n = w.getnframes()
    assert 0 < n <= 60 * 16000
    raw = w.readframes(n)
    assert len(raw) == n * 4
OUT.mkdir(parents=True, exist_ok=False)
report = {'input':str(INPUT), 'pcm_sha256':hashlib.sha256(raw).hexdigest(), 'frames':n, 'host_only':True, 'channels':[]}
samples = struct.unpack('<' + 'h' * (2*n), raw)
env = os.environ.copy()
env['PATH'] = str(R/'lib') + os.pathsep + env.get('PATH','')
for ch in range(2):
    x = samples[ch::2]
    mono = OUT / ('channel%d.wav' % ch)
    with wave.open(str(mono), 'wb') as w:
        w.setparams((1,2,16000,n,'NONE','not compressed'))
        w.writeframes(struct.pack('<'+'h'*n, *x))
    row = {'channel':ch, 'peak':max(map(abs,x)), 'rms':math.sqrt(sum(v*v for v in x)/n), 'nonzero':sum(v!=0 for v in x), 'rail_samples':sum(v in (-32768,32767) for v in x), 'wav_sha256':hashlib.sha256(mono.read_bytes()).hexdigest()}
    cmd = [str(R/'bin/sherpa-onnx.exe'), '--paraformer-encoder='+str(M/'encoder.int8.onnx'), '--paraformer-decoder='+str(M/'decoder.int8.onnx'), '--tokens='+str(M/'tokens.txt'), '--num-threads=1', '--provider=cpu', '--decoding-method=greedy_search', str(mono.resolve())]
    row['command'] = cmd
    start = time.monotonic()
    if not row['nonzero']:
        row['skipped'] = 'all-zero channel'
    else:
        with (OUT/('channel%d.stdout.raw'%ch)).open('xb') as so, (OUT/('channel%d.stderr.raw'%ch)).open('xb') as se:
            try:
                p = subprocess.run(cmd, cwd=OUT, env=env, stdout=so, stderr=se, timeout=120)
                row['exit_code'] = p.returncode
            except subprocess.TimeoutExpired:
                row['timed_out'] = True
    row['seconds'] = time.monotonic()-start
    report['channels'].append(row)
    (OUT/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
```

运行 Python 使用 `C:/Users/pc2025/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。原始 stdout/stderr 字节保留；旧执行输出混合本地路径代码页与 UTF-8 文本，不应以替换字符版本覆盖原始输出。若后续增加尾部静音，另存派生 WAV 和标记长度，不能悄悄替换主结果。
