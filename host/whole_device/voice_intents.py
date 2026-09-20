"""Deterministic command routing only; never execute raw ASR or model text."""
from collections import deque
import re

COMMANDS = {
    '测肤': 'assessment_start', '开始测肤': 'assessment_start',
    '皮肤检测': 'assessment_start', '开始皮肤检测': 'assessment_start',
    '停止云台': 'stop', '停止测肤': 'stop', '停止播报': 'stop',
}


class IntentRouter:
    def __init__(self):
        self.seen = deque(maxlen=128)

    def route(self, session_id, sentence_id, kind, text):
        if kind != 'final':
            return None
        if (not isinstance(session_id,str) or not session_id or
                type(sentence_id) is not int or sentence_id < 0 or
                not isinstance(text,str) or len(text)>4096):
            raise ValueError('invalid_recognition')
        key=(session_id,sentence_id)
        if key in self.seen:
            return None
        self.seen.append(key)
        normalized=re.sub(r'[\s，。！？,.!?：:]+','',text).lower()
        if not normalized:
            return None
        if any(word in normalized for word in ('停止云台','停止测肤','停止播报')):
            return 'stop'
        if any(word in normalized for word in ('不要','别启动','取消启动')):
            return 'chat'
        if normalized.startswith('你好'):
            return 'tracking_start'
        return COMMANDS.get(normalized,'chat')
