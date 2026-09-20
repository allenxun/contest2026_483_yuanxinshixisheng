// Browser/client adapter for the provided Alibaba speech-service gateway.
// The caller supplies REAL 16 kHz mono PCM. This does not resample microphone audio.
export function speechService(base = 'http://10.3.1.125:8000', {
  fetchImpl = globalThis.fetch, WebSocketImpl = globalThis.WebSocket,
} = {}) {
  const url = new URL(base);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
    throw new Error('Invalid speech service URL');
  const endpoint = path => new URL(path, url).href;
  return {
    async health(signal) {
      const response = await fetchImpl(endpoint('/health'), {signal});
      if (!response.ok) return false;
      return (await response.json()).status === 'ok'; // Service health, NOT K7 connectivity.
    },
    async tts(text, signal) {
      if (typeof text !== 'string' || !text.trim() || [...text.trim()].length > 1000)
        throw new Error('Invalid TTS text');
      const response = await fetchImpl(endpoint('/tts'), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text}), signal,
      });
      if (!response.ok || !response.headers.get('content-type')?.startsWith('audio/pcm'))
        throw new Error('TTS service failed');
      const pcm = await response.arrayBuffer();
      if (!pcm.byteLength || pcm.byteLength % 2) throw new Error('Invalid TTS PCM');
      return {pcm, sampleRate: 16000, channels: 1, encoding: 'pcm_s16le'};
    },
    stream(onEvent = () => {}) {
      const wsURL = new URL('/asr/stream', url);
      wsURL.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      const socket = new WebSocketImpl(wsURL.href);
      let state = 'connecting', next = 0, acknowledged = 0;
      const fail = code => {
        if (state === 'closed') return;
        state = 'closed'; socket.close(); onEvent({type: 'error', code});
      };
      socket.onopen = () => {
        if (state === 'closed') return;
        state = 'starting';
        socket.send(JSON.stringify({type: 'start', sample_rate: 16000, channels: 1,
          encoding: 'pcm_s16le', frame_ms: 20}));
      };
      socket.onmessage = message => {
        if (state === 'closed') return;
        try {
          const event = JSON.parse(message.data);
          if (event.type === 'ready' && state === 'starting') state = 'ready';
          else if (event.type === 'ack') {
            if (!Number.isInteger(event.next_seq) || event.next_seq < acknowledged || event.next_seq > next)
              throw new Error('Invalid ack');
            acknowledged = event.next_seq;
          } else if (['completed', 'cancelled', 'error'].includes(event.type)) {
            state = 'closed'; socket.close();
          } // Sentence final keeps the stream open.
          onEvent(event);
        } catch { fail('invalid_stream_event'); }
      };
      socket.onerror = () => fail('websocket_failed');
      socket.onclose = () => {
        if (state !== 'closed') { state = 'closed'; onEvent({type: 'disconnected'}); }
      };
      return {
        get ready() { return state === 'ready'; },
        // false means NOT accepted. Retry this same PCM after ack; no silent drops.
        sendPcm(pcm) {
          if (!(pcm instanceof Uint8Array) || pcm.byteLength !== 640)
            throw new Error('Expected one 20 ms / 640 byte PCM16 frame');
          if (state !== 'ready') throw new Error('ASR stream is not ready');
          if (next >= 3000) throw new Error('ASR duration limit');
          if (next - acknowledged >= 16 || socket.bufferedAmount > 16384) return false;
          const packet = new Uint8Array(644);
          new DataView(packet.buffer).setUint32(0, next, true);
          packet.set(pcm, 4); socket.send(packet); next++; return true;
        },
        stop() {
          if (state !== 'ready') throw new Error('ASR stream is not ready');
          state = 'draining'; socket.send(JSON.stringify({type: 'stop', next_seq: next}));
        },
        cancel() {
          if (state === 'closed') return;
          state = 'closed'; socket.close();
        },
      };
    },
  };
}
