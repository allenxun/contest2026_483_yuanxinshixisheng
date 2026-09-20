"""One synthetic public phrase through the configured local speech service."""
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from host.streaming_asr.client import run

async def main():
    out=ROOT/'evidence/speech-stream-live-20260914'/time.strftime('%Y%m%d-%H%M%S')
    out.mkdir(parents=True,exist_ok=True)
    result={'synthetic_audio_only':True,'board_tested':False,'credentials_saved':False}
    began=time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            response=await client.post('http://127.0.0.1:8000/tts',json={'text':'你好，联网成功。现在开始测试实时语音识别。'})
        result['tts_http_status']=response.status_code
        result['tts_ms']=round((time.monotonic()-began)*1000)
        if response.status_code!=200:
            raise RuntimeError('tts_failed')
        pcm=response.content
        if not response.headers.get('content-type','').startswith('audio/pcm') or not pcm or len(pcm)%2:
            raise RuntimeError('invalid_tts_pcm')
        result['pcm_bytes']=len(pcm)
        result['pcm_duration_ms']=len(pcm)/32
        result['stream']=await run('ws://127.0.0.1:8000/asr/stream',pcm)
        result['passed']=any(e['type']=='final' for e in result['stream']['events'])
    except Exception as exc:
        result['passed']=False
        result['error_type']=type(exc).__name__
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

asyncio.run(main())
