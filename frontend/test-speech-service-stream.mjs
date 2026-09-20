import test from 'node:test';
import assert from 'node:assert/strict';
import {speechService} from './speech-service-stream.mjs';
class Socket {
  static last;
  constructor() { Socket.last = this; this.sent = []; this.bufferedAmount = 0; }
  send(x) { this.sent.push(x); }
  close() { this.closed = true; }
  event(value) { this.onmessage({data: JSON.stringify(value)}); }
}
test('start, sequence, partial and sentence final keep duplex audio active', () => {
  const events = [];
  const session = speechService(undefined, {WebSocketImpl: Socket}).stream(x => events.push(x));
  const ws = Socket.last;
  ws.onopen(); ws.event({type: 'ready'});
  assert.equal(session.sendPcm(new Uint8Array(640)), true);
  assert.equal(new DataView(ws.sent[1].buffer).getUint32(0, true), 0);
  ws.event({type:'partial',text:'你'}); ws.event({type:'final',text:'你好'});
  assert.equal(session.ready, true);
  session.stop(); assert.equal(JSON.parse(ws.sent.at(-1)).next_seq,1);
  ws.event({type:'completed'}); assert.equal(ws.closed,true);
});
test('backpressure preserves next sequence and resumes after ack', () => {
  const session=speechService(undefined,{WebSocketImpl:Socket}).stream();
  const ws=Socket.last; ws.onopen(); ws.event({type:'ready'});
  for(let i=0;i<16;i++)assert.equal(session.sendPcm(new Uint8Array(640)),true);
  assert.equal(session.sendPcm(new Uint8Array(640)),false);
  ws.event({type:'ack',next_seq:1});
  assert.equal(session.sendPcm(new Uint8Array(640)),true);
  assert.equal(new DataView(ws.sent.at(-1).buffer).getUint32(0,true),16);
});
test('cancel ignores late ready and rejects new audio', () => {
  const session=speechService(undefined,{WebSocketImpl:Socket}).stream();
  const ws=Socket.last; session.cancel(); ws.event({type:'ready'});
  assert.equal(session.ready,false); assert.throws(()=>session.sendPcm(new Uint8Array(640)));
});
test('TTS JSON errors cannot be returned as playable PCM', async () => {
  const client=speechService(undefined,{fetchImpl:async()=>new Response('{}',{status:502})});
  await assert.rejects(client.tts('你好'));
});
