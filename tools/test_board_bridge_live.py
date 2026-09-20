"""Synthetic phrase validates the exact board wire against the real cloud."""
import asyncio,json,struct,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from host.streaming_asr.board_bridge import packet,read_packet

async def main():
 result={'synthetic':True,'board_tested':False}
 r,w=await asyncio.open_connection('127.0.0.1',8001)
 w.write(b'K7S1T');await w.drain()
 start=time.monotonic();await packet(w,b'T','联网成功'.encode())
 kind,pcm=await read_packet(r,960000)
 assert kind==b'D' and pcm and len(pcm)%2==0
 result.update(tts_bytes=len(pcm),tts_ms=round((time.monotonic()-start)*1000))
 w.close();await w.wait_closed();await asyncio.sleep(.2)
 r,w=await asyncio.open_connection('127.0.0.1',8001)
 w.write(b'K7S1A');await w.drain()
 _,raw=await read_packet(r,8192);assert json.loads(raw)['type']=='ready'
 start=time.monotonic();events=[]
 async def receive():
  while True:
   kind,raw=await read_packet(r,8192);assert kind==b'J'
   e=json.loads(raw);e['elapsed_ms']=round((time.monotonic()-start)*1000);events.append(e)
   if e['type']=='completed':return
 async def send():
  for seq,off in enumerate(range(0,len(pcm),640)):
   await asyncio.sleep(max(0,start+seq*.02-time.monotonic()))
   await packet(w,b'A',struct.pack('<I',seq)+pcm[off:off+640].ljust(640,b'\0'))
  await packet(w,b'E',b'')
 await asyncio.wait_for(asyncio.gather(send(),receive()),30)
 w.close();await w.wait_closed()
 result['events']=events
 result['passed']=any(e['type']=='final' and '联网成功' in e.get('text','') for e in events)
 path=ROOT/'evidence/board-speech-bridge-20260914'/('live-'+time.strftime('%H%M%S')+'.json')
 path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False))

asyncio.run(main())
