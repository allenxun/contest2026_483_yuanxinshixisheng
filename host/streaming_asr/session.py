"""Bounded, single-owner PCM framing and recognition-event lifecycle.

This module neither recognizes speech nor starts network connections. A future
transport adapter must drain frames and supply real upstream partial/final events.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
import re


class ProtocolError(ValueError):
    """Invalid message/state; the session is failed and queued data discarded."""


class BackpressureError(BufferError):
    """Audio was NOT accepted: drain pending frames, then retry the same sequence."""


class State(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    DRAINING = "draining"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


@dataclass(frozen=True)
class AudioFrame:
    seq: int
    pcm: bytes


@dataclass(frozen=True)
class RecognitionEvent:
    session_id: str
    kind: str
    revision: int
    text: str


class AsrSession:
    RATE_HZ = 16000
    CHANNELS = 1
    SAMPLE_BYTES = 2
    FRAME_MS = 20
    FRAME_BYTES = 640

    def __init__(self, *, max_pending_frames=50, max_total_frames=1500,
                 max_events=16, max_text_bytes=4096):
        # Bounds are themselves bounded, even when supplied by an integration.
        for value, ceiling in ((max_pending_frames, 500),
                               (max_total_frames, 30000),
                               (max_events, 256), (max_text_bytes, 65536)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid resource bound")
        self.max_pending_frames = max_pending_frames
        self.max_total_frames = max_total_frames
        self.max_events = max_events
        self.max_text_bytes = max_text_bytes
        self.state = State.IDLE
        self.session_id = None
        self.next_seq = 0
        self._revision = 0
        self._audio = deque()
        self._events = deque()

    def _clear(self):
        self._audio.clear()
        self._events.clear()

    def _fail(self, reason):
        self._clear()
        self.state = State.FAILED
        raise ProtocolError(reason)  # Never interpolate audio, text or credentials.

    def start(self, session_id, *, sample_rate=16000, channels=1,
              encoding="pcm_s16le", frame_ms=20):
        if self.state != State.IDLE:
            self._fail("session cannot restart; allocate a new session")
        if (not isinstance(session_id, str) or
                re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id) is None):
            self._fail("invalid session identifier")
        if (type(sample_rate) is not int or sample_rate != self.RATE_HZ or
                type(channels) is not int or channels != self.CHANNELS or
                encoding != "pcm_s16le" or type(frame_ms) is not int or
                frame_ms != self.FRAME_MS):
            self._fail("unsupported audio format")
        self.session_id = session_id
        self.state = State.ACTIVE

    def audio(self, seq, pcm):
        if self.state != State.ACTIVE:
            self._fail("audio requires active session")
        if type(seq) is not int or seq != self.next_seq:
            self._fail("audio sequence mismatch")
        if not isinstance(pcm, bytes) or len(pcm) != self.FRAME_BYTES:
            self._fail("audio must be one 640-byte PCM frame")
        if self.next_seq >= self.max_total_frames:
            self._fail("session audio duration limit")
        if len(self._audio) >= self.max_pending_frames:
            raise BackpressureError("audio queue full; frame not accepted")
        self._audio.append(AudioFrame(seq, pcm))
        self.next_seq += 1

    def take_audio(self):
        """Consume exactly one accepted frame, or None. Caller owns its lifetime."""
        return self._audio.popleft() if self._audio else None

    def stop(self, next_seq):
        """Seal input. Send upstream finish only once upstream_finish_ready is true."""
        if (self.state != State.ACTIVE or type(next_seq) is not int or
                next_seq != self.next_seq):
            self._fail("invalid stop sequence or state")
        self.state = State.DRAINING

    @property
    def upstream_finish_ready(self):
        # The adapter must also account for any frame it has taken but not sent.
        return self.state == State.DRAINING and not self._audio

    @property
    def pending_audio(self):
        return len(self._audio)

    @property
    def pending_events(self):
        return len(self._events)

    def _recognition(self, session_id, text, final):
        # Late callbacks from closed sessions are ignored, not resurrected.
        if self.state in (State.CANCELLED, State.DISCONNECTED, State.FAILED,
                          State.COMPLETED):
            return False
        if self.state not in (State.ACTIVE, State.DRAINING):
            self._fail("recognition requires started session")
        if session_id != self.session_id:
            self._fail("recognition session mismatch")
        if not isinstance(text, str):
            self._fail("invalid recognition text")
        # Avoid encoding an arbitrarily large string before checking its bound.
        if len(text) > self.max_text_bytes:
            self._fail("recognition text limit")
        try:
            encoded_size = len(text.encode("utf-8"))
        except UnicodeError:
            self._fail("invalid recognition text encoding")
        if encoded_size > self.max_text_bytes:
            self._fail("recognition text limit")
        self._revision += 1
        # Queue is a bounded history; partials are snapshots, never text deltas.
        # A final always wins space over oldest unconsumed partials.
        if len(self._events) >= self.max_events:
            self._events.popleft()
        self._events.append(RecognitionEvent(
            self.session_id, "final" if final else "partial", self._revision, text))
        if final:
            self._audio.clear()
            self.state = State.COMPLETED
        return True

    def partial(self, session_id, text):
        return self._recognition(session_id, text, False)

    def final(self, session_id, text):
        """One real upstream final closes this utterance, including auto endpoint."""
        return self._recognition(session_id, text, True)

    def take_event(self):
        return self._events.popleft() if self._events else None

    def cancel(self):
        self._clear()
        if self.state != State.DISCONNECTED:
            self.state = State.CANCELLED

    def disconnect(self):
        self._clear()
        self.state = State.DISCONNECTED
