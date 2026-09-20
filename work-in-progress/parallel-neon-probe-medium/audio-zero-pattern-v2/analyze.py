"""Read-only input audit. Outputs only within this candidate directory."""
import hashlib, json, pathlib, re, shutil, struct, wave
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
paths = [
 'evidence/audio-input-20260910/k7sound-capture-pga24-48000-20260910-204030.bin',
 'evidence/audio-input-20260910/k7sound-dump-20260910-204101.bin',
 'evidence/audio-input-20260910/voice-pga24-first/capture-raw32.wav',
 'evidence/audio-input-20260910/voice-pga24-first/extraction.json',
 'evidence/audio-sai-trm-20260910/SAI-layout.txt',
 'evidence/audio-sai-trm-20260910/SAI-application.txt',
 'evidence/audio-sai-trm-20260910/input.json',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.c',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.h',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.c',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.h',
 'app/k7sound/pio.c', 'app/k7sound/pio.h', 'app/k7sound/k7sound_main.c',
 'app/k7sound/observe.c', 'app/k7sound/observe.h']
manifest = []
for name in paths:
    data = (ROOT / name).read_bytes()
    dest = HERE / 'input' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        assert dest.read_bytes() == data, 'Frozen input changed; use new candidate'
    else:
        dest.write_bytes(data)
    manifest.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
(HERE / 'inputs.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
with wave.open(str(HERE / 'input' / paths[2]), 'rb') as wav:
    assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (2,4,16000,48000)
    raw = wav.readframes(48000)
words = struct.unpack('<96000i', raw)
dump = (HERE / 'input' / paths[1]).read_text(encoding='ascii')
dump_words = []
for offset, body in re.findall(r'^PCM ([0-9a-f]+) ((?:[0-9a-f]{8} ?)+)\r?$', dump, re.M):
    assert int(offset,16) == len(dump_words)
    dump_words.extend(int(x,16) for x in body.split())
assert len(dump_words) == 96000
assert b''.join(struct.pack('<I', w) for w in dump_words) == raw
counts = [[sum(words[2*i+c] != 0 for i in range(p,48000,4)) for p in range(4)] for c in range(2)]
log = (HERE / 'input' / paths[0]).read_text(encoding='ascii')
records = re.findall(r'trace_word index=(\d+) us=(\d+) before=([0-9a-f]+) word=([0-9a-f]+) after=([0-9a-f]+) rc=0,0,0', log)
assert len(records) == 32
banks = []
for n, us, before, word, after in records:
    n,before,after = int(n),int(before,16),int(after,16)
    bank = (n//2)%4
    assert before == (2-n%2) << (6*bank)
    assert after == (1-n%2) << (6*bank)
    if bank:
        assert int(word,16) == 0
    banks.append(bank)
assert counts == [[12000,0,0,0],[11999,0,0,0]]
result = dict(frames=48000, channels=2, rate=16000, nonzero_by_frame_mod4=counts,
              trace_words=32, trace_banks=banks,
              first_pair_intervals_us=[int(records[i][1])-int(records[i-2][1]) for i in range(2,32,2)],
              observed_codec={k:v for k,v in re.findall(r'codec reg=([0-9a-f]+) value=([0-9a-f]+)',log)},
              conclusion='Three zero phases preserved; valid FIFO entries consumed; cause unresolved. No resampling performed.')
(HERE / 'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
print('PASS: frozen WAV phase counts and all 32 real FIFO transitions checked')
