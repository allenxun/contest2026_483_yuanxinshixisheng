"""Pace raw PCM into the real duplex route; results arrive during capture/send."""
import argparse
import asyncio
import json
from pathlib import Path
import struct
import time
from websockets.asyncio.client import connect


async def run(url, pcm):
    if not pcm or len(pcm) % 2 or len(pcm) > 3000 * 640:
        raise ValueError('PCM must be nonempty mono S16LE, at most 60 seconds')
    async with connect(url, max_size=65536, max_queue=4) as socket:
        await socket.send(json.dumps({'type':'start','sample_rate':16000,
                                     'channels':1,'encoding':'pcm_s16le','frame_ms':20}))
        ready=json.loads(await asyncio.wait_for(socket.recv(),15))
        if ready.get('type')!='ready':
            raise RuntimeError('stream did not become ready')
        began=time.monotonic()
        ack=asyncio.Event()
        frames=(len(pcm)+639)//640
        async def send():
            for seq in range(frames):
                await asyncio.sleep(max(0,began+seq*.02-time.monotonic()))
                ack.clear()
                await socket.send(struct.pack('<I',seq)+pcm[seq*640:(seq+1)*640].ljust(640,b'\0'))
                await asyncio.wait_for(ack.wait(),10)
            await socket.send(json.dumps({'type':'stop','next_seq':frames}))
        async def receive():
            results=[]
            while True:
                event=json.loads(await asyncio.wait_for(socket.recv(),20))
                if event.get('type')=='ack':
                    ack.set()
                else:
                    event['elapsed_ms']=round((time.monotonic()-began)*1000)
                    results.append(event)
                if event.get('type')=='error': raise RuntimeError('stream failed')
                if event.get('type')=='completed': return results
        sender=asyncio.create_task(send())
        receiver=asyncio.create_task(receive())
        try:
            _, events=await asyncio.wait_for(asyncio.gather(sender,receiver),80)
            return {'frames':frames,'events':events}
        finally:
            sender.cancel(); receiver.cancel()
            await asyncio.gather(sender,receiver,return_exceptions=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('pcm',type=Path)
    parser.add_argument('--url',default='ws://127.0.0.1:8000/asr/stream')
    args=parser.parse_args()
    print(json.dumps(asyncio.run(run(args.url,args.pcm.read_bytes())),ensure_ascii=False))
