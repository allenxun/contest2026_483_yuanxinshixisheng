"""Fixed commands for a pre-initialized voicecam session, never raw ASR text.

This adapter does not adopt MCU coordinates or start the camera automatically.
Its caller must arrange the calibrated voicecam session and own serial access.
"""
import re


class NativeMotion:
    def __init__(self, serial):
        self.serial = serial

    async def set_mode(self, mode):
        number = {'track': 1, 'photo': 2}.get(mode)
        if number is None:
            raise ValueError('invalid_motion_mode')
        def reply(line):
            applied = re.fullmatch(r'VOICE MODE applied=([012]) result=(-?\d+)', line)
            if applied:
                return int(applied[2]) < 0 or int(applied[1]) == number
            failed = re.fullmatch(r'VOICE MODE requested=([012]) result=(-?\d+)', line)
            return bool(failed and int(failed[1]) == number and int(failed[2]) < 0)
        line = await self.serial.request('motion-mode', 'k7host voicemode '+mode,
                                         reply, timeout=10)
        return line == f'VOICE MODE applied={number} result=0'

    async def stop(self):
        # This exact line is printed after the board sets its atomic hold flag.
        # It confirms software hold, not a motor power-off or physical MCU ACK.
        expected = 'TRACK halt requested: hold last target; not motor disable.'
        line = await self.serial.request('motion-stop', 'k7host halt',
                                         lambda line: line == expected, timeout=3)
        return line == expected
