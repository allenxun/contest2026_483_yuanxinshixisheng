"""Keep the unsuccessful normal-power comparison and next-build state."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1];E=R/'evidence/audio-normal-20260910'
obs=[]
for p in sorted(E.glob('k7sound-*.json')):
    d=json.loads(p.read_text());assert hashlib.sha256((E/d['raw']).read_bytes()).hexdigest()==d['raw_sha256'];obs.append(d)
result=dict(revision='audio-normal-20260910',firmware_sha256='e625c8aee64b166f2e192485d4a50060a4f4d4f28aa85e650a57cc9fa816eeaf',
 normal_power_readback_passed=True,microphone_audio_passed=False,capture_all_zero=True,
 adc_mute_bit_cleared=True,adc_0f_readback='20',adc_0f_undefined_bit4_not_failure=True,
 sdi_pull_raw='00005555',sdi_pull='pulldown, IO_1 encoding1',path='0000e4e4',
 gpio_4096_samples_all_low=True,observation_cannot_prove_missing_external_clock=True,observations=obs)
with (E/'runtime-results.json').open('x') as f:json.dump(result,f,indent=2)
p=R/'project-manifest.json';m=json.loads(p.read_text());m['updated_at']=datetime.now(timezone.utc).isoformat()
m['current_device']=dict(state='U-Boot RAM loading',running_revision=None,last_loaded_revision=result['revision'],
 wifi_connected=False,ble_connected=False,serial_observer_running=True,serial_owner='uart_load_audio_mic.py',emmc_written=False)
m['pending_firmware']=dict(revision='audio-mic-20260910',state='ELF/bin verified, RAM load in progress',
 sha256='b4a151d83b75669770769dfefd2a13c092194b658b89d7849ca3facd158976c3')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for rel in ['docs/板载音频接入状态_20260910.md','docs/代码日志对应表.md']:
    with (R/rel).open('a',encoding='utf-8') as f:
        f.write('\n\n2026-09-10 19:05 audio-normal实测：正常功耗寄存器读回成功，但3200帧仍全零；0f=20只比写30少未定义bit4，mute位已清，不判静音。SDI0下拉、PATH=e4e4、GPIO有限采样全低。进一步从精确官方clk-out.c确认独立IOC26046400 bit1主时钟输出门控遗漏，audio-mic补齐该门控与官方pull_none、20ms只读引脚观察，并加入独立reset的ADC对照模式；合并平台两组O0/O2测试、ARM64编译/ELF通过，RAM加载中。见各版本evidence，未宣称麦克风成功。\n')
print('Normal-power negative result retained; next MCLK/pad experiment pending')
