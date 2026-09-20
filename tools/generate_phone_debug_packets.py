"""Create synthetic-only manual BLE packets; never reads real credentials."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
command=dict(v=1,id=103,cmd='submit_credentials',ssid_b64='TGFuc2Vl',password='EXAMPLE_ONLY_123')
data=(json.dumps(command,separators=(',',':'))+'\n').encode('ascii')
packets=[data[i:i+20] for i in range(0,len(data),20)]
assert b''.join(packets)==data and packets[-1][-1]==10
lines=['仅使用测试密码，不会连接 Wi-Fi。',
       '先在 Notify 开启通知；在 Write 的 HEX 模式下顺序发送下面数据，每行等写入完成；全部片段须在 10 秒内发完。',
       'X 扫描命令单独发送：58',
       '以下为提交 Lansee + 测试密码 EXAMPLE_ONLY_123 的分包；末包含 0A：','']
lines += [packet.hex(' ').upper() for packet in packets]
(ROOT/'frontend/手机调试HEX分包.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(packet_count=len(packets),packet_lengths=[len(p) for p in packets],synthetic_only=True)))
