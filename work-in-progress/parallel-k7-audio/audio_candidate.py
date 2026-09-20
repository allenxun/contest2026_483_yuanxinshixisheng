"""Host-only preparation: no register access, device opens, or network.

BoardProfile records a proposed explicit clock profile, not observed hardware.
Backend.perform is blocking; False can mean a partially completed action.
Only Backend.quiesce confirming all DMA/clock/codec work has exited releases a lease.
"""
from dataclasses import dataclass
from enum import Enum

class State(Enum):
    IDLE='idle'
    PREPARING='preparing'
    CAPTURING='capturing'
    DRAINING='draining'

@dataclass(frozen=True)
class BoardProfile:
    # Requested 16 kHz, two 16-bit I2S slots. Must measure on the actual board.
    rate:int=16000
    slots:int=2
    slot_bits:int=16
    mclk:int=4096000
    codec_address:int=0x10
    def validate(self):
        if (self.rate,self.slots,self.slot_bits,self.mclk,self.codec_address)!=(16000,2,16,4096000,0x10):
            raise ValueError('profile not reviewed')
    @property
    def bclk(self):
        return self.rate*self.slots*self.slot_bits

class CaptureSession:
    """Serialized owner, capacity one. Context manager requires explicit drain ACK.

    Cleanup failure remains DRAINING; retaining this object alone cannot retain
    board memory. Actual backend must retain DMA allocations beyond this object.
    No __del__ hardware cleanup is claimed, since Python GC is not deterministic.
    """
    def __init__(self,backend,profile=BoardProfile()):
        profile.validate();self.backend=backend;self.profile=profile
        self.state=State.IDLE;self.transaction=0;self.error=None
    def start(self,now_ms,deadline_ms,verified=False):
        if self.state!=State.IDLE:return False
        if not verified:raise ValueError('board identity/rails/pins/codec route unverified')
        if deadline_ms<=now_ms():return False
        self.transaction+=1;self.error=None;self.state=State.PREPARING
        # Semantic plan only: backend must implement reviewed board register steps.
        # Amp stays disabled for capture; codec probe reference is NOT a mute API.
        actions=('amp_disable','verify_rails','configure_i2c3_m0','codec_ack_0x10',
                 'configure_sai1_m0','enable_audio_clocks','reset_sai',
                 'codec_reset_and_capture_route','configure_i2s_16k_2x16',
                 'prepare_rx_dma','start_rx')
        try:
            for action in actions:
                if now_ms()>=deadline_ms:raise TimeoutError('deadline before action')
                if not self.backend.perform(action,self.transaction,self.profile):
                    raise RuntimeError(action)
                if now_ms()>=deadline_ms:raise TimeoutError('deadline after blocking action')
            self.state=State.CAPTURING;return True
        except Exception as e:
            self.error=type(e).__name__+': '+str(e);self.stop();return False
    def stop(self):
        if self.state==State.IDLE:return True
        self.state=State.DRAINING
        try:
            if self.backend.quiesce(self.transaction):self.state=State.IDLE;return True
        except Exception as e:self.error='cleanup: '+str(e)
        return False
    def release_ack(self,transaction):
        # Serialized trusted ACK; call only after actual backend quiescence.
        if transaction!=self.transaction or self.state!=State.DRAINING:return False
        self.state=State.IDLE;return True

class Pcm16Channels:
    """PCM16 LE streaming channel conversion; NO sample-rate conversion.

    Up to 4096 input bytes per push; retains < one input frame. Same-rate mono
    duplication, stereo left/right/mean supported. Rejections leave state intact.
    finish rejects truncated frames instead of zero-padding them silently.
    """
    def __init__(self,in_rate,out_rate,in_channels,out_channels,select='left'):
        if in_rate!=out_rate or in_rate not in (8000,16000,44100,48000):
            raise ValueError('resampler required or unsupported sample rate')
        if in_channels not in (1,2) or out_channels not in (1,2) or select not in ('left','right','mean'):
            raise ValueError('format')
        self.ic=in_channels;self.oc=out_channels;self.select=select;self.pending=b'';self.closed=False
    def push(self,data):
        if self.closed or len(data)>4096:raise ValueError('closed/capacity')
        merged=self.pending+bytes(data);frame=self.ic*2;count=len(merged)//frame
        output=bytearray()
        for i in range(count):
            part=merged[i*frame:(i+1)*frame]
            left=int.from_bytes(part[:2],'little',signed=True)
            right=int.from_bytes(part[2:4],'little',signed=True) if self.ic==2 else left
            if self.oc==1:
                value=left if self.select=='left' else right if self.select=='right' else int((left+right)/2)
                output.extend(value.to_bytes(2,'little',signed=True))
            else:
                output.extend(left.to_bytes(2,'little',signed=True));output.extend(right.to_bytes(2,'little',signed=True))
        self.pending=merged[count*frame:];return bytes(output)
    def finish(self):
        self.closed=True
        if self.pending:raise ValueError('incomplete PCM frame')

class FullSpeedPacketPlan:
    """Host math for synchronous UAC1 FS 1 ms PCM16 only, not USB negotiation.
    Async/adaptive/feedback/high-speed endpoints intentionally need another plan.
    """
    def __init__(self,rate,channels,max_packet,sync='synchronous',interval_ms=1):
        if rate not in (8000,16000,44100,48000) or channels not in (1,2):raise ValueError('format')
        if sync!='synchronous' or interval_ms!=1:raise ValueError('clock/interval unsupported')
        if max_packet<((rate+999)//1000)*channels*2 or max_packet>1023:raise ValueError('endpoint capacity')
        self.rate=rate;self.channels=channels;self.remainder=0
    def next_bytes(self):
        frames,self.remainder=divmod(self.remainder+self.rate,1000)
        return frames*self.channels*2
