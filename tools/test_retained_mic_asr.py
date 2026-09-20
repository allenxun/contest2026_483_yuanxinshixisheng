"""Send only the complete retained microphone recording through live ASR."""
import asyncio,json,sys,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from host.streaming_asr.live_client import run_live
async def main():
 folder=ROOT/'evidence/stage-watch-20260916'
 assert json.loads((folder/'mic-mono-coverage.json').read_text())['complete']
 with wave.open(str(folder/'mic-mono-channel-0.wav'),'rb') as w:
  assert (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getnframes())==(1,2,16000,48000)
  pcm=w.readframes(48000)
 events=[]
 async def frames():
  for off in range(0,len(pcm),640):
   yield pcm[off:off+640]
   await asyncio.sleep(.02)
 async def event(e):
  if e.get('type') in ['ready','partial','final','completed','error']:
   events.append(e);print(json.dumps(e,ensure_ascii=False),flush=True)
 result=await run_live('ws://127.0.0.1:8000/asr/stream',frames(),event)
 (folder/'retained-mic-asr.json').write_text(json.dumps({'source':'mic-mono-channel-0.wav','live_board':False,'result':result,'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(main())
