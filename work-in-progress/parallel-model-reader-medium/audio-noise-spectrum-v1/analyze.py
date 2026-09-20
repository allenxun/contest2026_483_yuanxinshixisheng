"""Host-only analysis/derived WAV; no playback, hardware, ASR, normalization."""
import hashlib,json,math,pathlib,wave
import numpy as np
R=pathlib.Path(__file__).resolve().parent
P=R.parents[2]/'evidence/audio-gain-20260910/voice-max-first/capture-raw32.wav'
def avg4(x):
    y=np.zeros_like(x,dtype=np.int64)
    for k in range(4):
        if k==0:y+=x
        else:y[k:]+=x[:-k]
    # Symmetric integer truncation toward zero, no gain or normalization.
    return np.where(y<0,-((-y)//4),y//4).astype('<i4')
imp=np.array([[400,-400],[0,0],[0,0],[0,0],[0,0]],dtype=np.int64)
assert avg4(imp).tolist()==[[100,-100]]*4+[[0,0]]
assert avg4(np.full((8,2),400,dtype=np.int64))[3:].tolist()==[[400,400]]*5
assert not np.any(avg4(np.zeros((8,2),dtype=np.int64)))
assert avg4(np.array([[2147483647,-2147483648]]*8,dtype=np.int64))[-1].tolist()==[2147483647,-2147483648]
with wave.open(str(P),'rb') as w:
    assert (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())==(2,4,16000,'NONE')
    n=w.getnframes();raw=w.readframes(n);assert n>4 and len(raw)==n*8
x=np.frombuffer(raw,dtype='<i4').reshape(-1,2).astype(np.int64)
y=avg4(x)
dest=R/'derived-ma4-causal-stereo32-16000.wav'
with wave.open(str(dest),'wb') as w:
    w.setparams((2,4,16000,n,'NONE','not compressed'));w.writeframes(y.tobytes())
assert np.max(np.abs(y.astype(np.int64)))<=np.max(np.abs(x))
with wave.open(str(dest),'rb') as w:assert w.getnframes()==n and w.getframerate()==16000 and w.getnchannels()==2
freq=np.fft.rfftfreq(n,1/16000)
window=np.hanning(n)
bands=[(20,1000),(1000,2000),(2000,3000),(3000,5000),(5000,7000),(7000,8001)]
def summary(a):
    rows=[]
    for c in range(2):
        z=a[:,c].astype(np.float64);mean=float(z.mean());rms=float(np.sqrt(np.mean(z*z)))
        spec=np.abs(np.fft.rfft((z-mean)*window))**2
        total=float(spec[(freq>=20)].sum())
        row={'channel':c,'mean':mean,'peak':int(np.max(np.abs(z))),'rms':rms,'rms_dbfs':20*math.log10(rms/2**31) if rms else None,'nonzero_mod4':[int(np.count_nonzero(a[k::4,c])) for k in range(4)],'bands':[]}
        for lo,hi in bands:
            sel=(freq>=lo)&(freq<hi);power=float(spec[sel].sum())
            row['bands'].append({'hz':[lo,hi],'power':power,'fraction_of_ac_20hz_up':power/total if total else None})
        indices=np.where(freq>=20)[0];best=indices[np.argsort(spec[indices])[-8:][::-1]]
        row['strongest_bins_hz']=[float(freq[i]) for i in best]
        # Relative spectral-periodicity error, no physical-rate inference.
        rectangular=np.abs(np.fft.fft(z))
        if n%4==0:
            shifted=np.roll(rectangular,n//4)
            row['fft_magnitude_4khz_shift_relative_error']=float(np.linalg.norm(rectangular-shifted)/np.linalg.norm(rectangular))
        rows.append(row)
    return rows
report={'source':str(P),'source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'frames':n,'declared_rate':16000,'seconds':n/16000,'numpy_version':np.__version__,'source_stats':summary(x),'derived_stats':summary(y),'derived':dest.name,'derived_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'filter':{'type':'causal four-tap moving average independently per channel','coefficients':[.25]*4,'delay_samples':1.5,'delay_us_at_declared_rate':93.75,'startup':'three leading zero history samples','end':'same frame count, final3 convolution-tail frames not appended','normalization':False,'cross_channel_mix':False},'tests':'impulse,constant,zero,int32 extrema,no peak increase,WAV metadata PASS','analysis':'Hann window, per-channel DC removal for spectrum, energy fractions relative >=20Hz. Does not prove true serial sampling rate or ADC noise source.'}
(R/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
(R/'delivery.json').write_text(json.dumps([{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(R.iterdir()) if p.is_file() and p.name!='delivery.json'],indent=2),encoding='utf-8')
