"""Connect normalized final ASR events to the device controller.

One active recording session prevents late cloud results from starting motion.
The caller continues reading ASR while a controller operation is running.
No hardware is opened here and ordinary speech is not treated as a command.
"""
from .voice_intents import IntentRouter


class CommandSession:
    def __init__(self, controller):
        self.controller = controller
        self.router = IntentRouter()
        self.session_id = None

    def begin(self, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('invalid_session_id')
        self.session_id = session_id

    def end(self):
        self.session_id = None

    async def accept(self, session_id, sentence_id, kind, text):
        if self.session_id is None or session_id != self.session_id:
            return 'stale'
        intent = self.router.route(session_id, sentence_id, kind, text)
        if intent is None:
            return 'ignored'
        if intent == 'stop':
            return 'stopped' if await self.controller.stop() else 'stop_unconfirmed'
        if intent == 'chat':
            return 'chat'
        return 'started' if self.controller.start(intent) else 'busy'
