from spoken_panel import ProgressParser


def test_parser():
    events = []
    parser = ProgressParser(lambda *event: events.append(event))
    parser.feed(b'TTS_AUDIO frames=16000 rate=8000 peak_milli=812 clipped=0 '
                b'cache=hit seconds=0.852 speakers=174 sid=21\n')
    parser.feed(b'VOICE_PROVISION_STATUS phase=2 state=0 grammar=0 turn=1 '
                b'candidates=0 selected=0 password_length=0\n')
    parser.feed(b'ASR_INFER BEGIN recognizer\n')
    parser.feed(b'ASR_CACHE hit=1 init_seconds=0.004\n')
    parser.feed(b'VOICE_PROVISION_STATUS phase=2 state=3 grammar=2 turn=3 '
                b'candidates=5 selected=1 password_length=4\n')
    assert any('8000 Hz' in (event[2] or '') for event in events)
    assert any('男声 ID 21/174' in (event[2] or '') for event in events)
    assert any('ASR：缓存 hit' in (event[2] or '') for event in events)
    assert any(event[0] == '等待唤醒' and '正在录音' in event[1] for event in events)
    assert any(event[0] == '正在识别' for event in events)
    assert any(event[0] == '请输入密码' and '已输入 4 个密码字符' in event[2]
               for event in events)


if __name__ == '__main__':
    test_parser()
    print('spoken panel parser PASS')
