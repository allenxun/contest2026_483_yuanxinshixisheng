"""Explicit fixed-audio transport benchmark, not a microphone/ASR test.

Stop the development bridge first; run this foreground; restore it afterwards.
"""
import asyncio, hashlib, json, time, sys, argparse
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
import httpx
from host.streaming_asr.board_bridge import audio_packet,read_packet
from cloud_radio_stage_audit import remote,ROOT

CODE=r'''
import serial,time,json
with serial.Serial('/dev/ttyUSB0',1500000,timeout=.02,write_timeout=2) as s:
 s.dtr=False;s.rts=False
 start=time.monotonic()
 for c in b'k7cloud tts-test 10.3.1.125\r':s.write(bytes([c]));s.flush();time.sleep(.004)
 out=bytearray()
 while time.monotonic()-start<45:
  out.extend(s.read(8192))
  if b'nsh>' in out:break
 print(json.dumps({'command_ms':round((time.monotonic()-start)*1000),'success':b'K7CLOUD tts result=0' in out,'console':out.decode(errors='replace')}))
'''

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--pcm');parser.add_argument('--once',action='store_true');args=parser.parse_args()
 out=ROOT/'evidence/tts-delivery-replays'/time.strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True,exist_ok=False)
 if args.pcm:
  pcm=__import__('pathlib').Path(args.pcm).read_bytes()
 else:
  async with httpx.AsyncClient(timeout=45) as client:
   response=await client.post('http://127.0.0.1:8000/tts',json={'text':'你好，今天天气怎么样？'})
   response.raise_for_status();pcm=response.content
  if not response.headers.get('content-type','').startswith('audio/pcm'):raise ValueError('invalid PCM type')
 if not pcm or len(pcm)%2 or len(pcm)>960000:raise ValueError('invalid PCM')
 results=[]
 for interval in ((0,) if args.once else (0,5,0,5)):
  completion=asyncio.get_running_loop().create_future()
  async def accept(reader,writer):
   try:
    if await reader.readexactly(5)!=b'K7S1T':raise ValueError('unexpected mode')
    kind,_=await read_packet(reader,3000)
    if kind!=b'T':raise ValueError('unexpected request')
    start=time.monotonic();await audio_packet(writer,pcm,interval)
    completion.set_result(round((time.monotonic()-start)*1000))
   except Exception as exc:
    if not completion.done():completion.set_exception(exc)
   finally:
    writer.close();await writer.wait_closed()
  server=await asyncio.start_server(accept,'0.0.0.0',8001)
  async with server:
   result=json.loads(await asyncio.to_thread(remote,CODE))
   result['host_enqueue_ms']=await asyncio.wait_for(completion,5)
  (out/('transport-'+str(len(results))+'.log')).write_text(result.pop('console'),encoding='utf-8')
  result['interval_ms']=interval;results.append(result);print(json.dumps(result),flush=True)
  if not result['success']:break
 report={'scope':'identical fixed PCM transport/playback; excludes cloud synthesis and ASR','pcm_bytes':len(pcm),'sha256':hashlib.sha256(pcm).hexdigest(),'audio_ms':len(pcm)/32,'runs':results}
 (out/'transport-comparison.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':asyncio.run(main())
