# Real captured WAV: periodic images and MA4 diagnostic derivative

The original source has exactly one potentially nonzero stereo frame in every4 stored frames: both channels' nonzero counts by index modulo4 are[12000,0,0,0]. Its unwindowed FFT magnitude repeats every4kHz (at the declared16kHz rate) with relative numerical error about3e-16. This is strong mathematical evidence of spectral images caused by the sparse sequence. It does not locate the hardware cause or prove physical16kHz ADC sampling.

Original SHA256:122e6fd4fafc052477fbd4806249d59e80d039e9ff7de2ced7f8344ebe7bf962. WAV metadata:48000 frames, stereo signedPCM32,16000Hz,3seconds. Original file untouched.

| Metric, left channel (right similar) | Original | Derived MA4 |
|---|---:|---:|
|RMS dBFS|-55.542|-61.562|
|Peak integer|44046592|11011648|
|3–5kHz share of measured AC spectrum|49.34%|0.801%|
|7–8kHz share|24.69%|0.195%|

Band fractions use Hann-window FFT with per-channel DC removed, denominator frequencies20Hz and above. The **absolute** integrated3–5kHz band power decreases about24.0dB; fraction changes alone should not be confused with absolute attenuation. Major original bins include50Hz,3950Hz,4050Hz,7950Hz;144Hz also has corresponding images.50Hz may be a hum/noise candidate but its frequency alone does not identify mains, wiring, ADC bias or any physical cause. A strong high-frequency image can contribute audible buzz/harshness, but no listening test was performed here.

`derived-ma4-causal-stereo32-16000.wav` is explicitly derived: y[n,c]=(x[n,c]+x[n−1,c]+x[n−2,c]+x[n−3,c])/4, computed independently for each channel with int64 intermediate and integer truncation towardzero. No gain normalization, no L/R averaging, no discarded frames, no changed sample rate. Output remains48000 stereoPCM32 frames. Three initial history samples arezero; no extra3 tail frames appended. Linear-phase group delay1.5frames=93.75us at the declared rate. For this exact sparse input, peak falls12.04dB and RMS6.02dB; the derivative may sound quieter, so a subjective noise comparison must record this difference rather than silently normalize.

MA4 has unity DC gain and zeros at4kHz and8kHz. Its magnitude is abs(sin(4*pi*f/Fs)/(4*sin(pi*f/Fs))); it also attenuates wanted higher frequencies and cannot reconstruct lost samples. In this particular input it spreads each isolated sample across4 output positions at one-quarter amplitude. This is a diagnostic low-pass comparison, not repaired capture, not proof of correct16kHz, and not a proposal to mask the FIFO issue. Root decides if/when a separate board playback comparison is useful after PGA24; no integration performed.

Reproduce: run `analyze.py` with C:/Users/pc2025/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe. Uses existing NumPy2.3.5; no dependency installation/download. Host tests passed: independent bipolar impulse response, constant/zero response, int32 extremes without overflow, no peak increase, frame/rate/channel preservation. analysis.json records complete band powers, per-channel statistics, source/derived hashes and filter parameters. No ASR, device, SDK or formal-source access occurred.

Derived SHA256:1b6d20cf31f96341b9c671017031b758de36683752242f409b27e8053c967eb7. User's current result remains “requires careful listening, with noise”; this file has not been declared intelligible or listened to by this agent.
