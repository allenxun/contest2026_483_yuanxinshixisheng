"""Ubuntu GTK panel for the complete board-side spoken Wi-Fi flow."""
import argparse
import datetime
from pathlib import Path
import re
import threading
import time


STATE_TEXT = {
    0: ('等待唤醒', '听完板载语音后，说“你好联网”。'),
    1: ('正在扫描 Wi-Fi', '请稍候，板端正在读取真实网络列表。'),
    2: ('请选择网络', '听完网络列表后，说对应的序号。'),
    3: ('请输入密码', '逐个说密码字符；界面和日志不会显示密码内容。'),
    4: ('等待确认', '核对播报的密码长度，然后说“确认提交”。'),
    5: ('已接收配网信息', '板端正在提交本次配网事务。'),
    6: ('正在连接 Wi-Fi', '正在等待认证、DHCP 和真实 IP。'),
    7: ('联网成功', '板端已取得真实 IP，完整语音配网通过。'),
    8: ('流程失败', '请查看下方错误和本轮日志。'),
    9: ('本轮已结束', '可以重新开始测试。'),
}


class ProgressParser:
    def __init__(self, update):
        self.update = update
        self.tail = b''
        self.last_status = None
        self.last_audio = None
        self.last_asr_cache = None

    def feed(self, block):
        data = self.tail + block
        self.tail = data[-4096:]
        audio = list(re.finditer(
            rb'TTS_AUDIO frames=(\d+) rate=(\d+) peak_milli=(\d+) clipped=(\d+)'
            rb'(?: cache=(hit|miss) seconds=([0-9.]+) speakers=(\d+) sid=(\d+))?', data))
        if audio:
            match = audio[-1]
            core = tuple(map(int, match.groups()[:4]))
            detail = match.groups()[4:]
            values = core + detail
            if values != self.last_audio:
                self.last_audio = values
                frames, rate, peak, clipped = core
                diagnostic = (f'TTS：{rate} Hz · {frames} 帧 · 峰值 {peak / 1000:.3f} '
                              f'· 削波 {clipped}')
                if detail[0]:
                    diagnostic += (f' · 缓存 {detail[0].decode()} · {float(detail[1]):.3f} 秒 '
                                   f'· 男声 ID {int(detail[3])}/{int(detail[2])}')
                self.update('正在语音播报',
                            '请听完板载提示后再说话。',
                            diagnostic)
        if (b'ASR_INFER BEGIN recognizer' in block or
                b'ASR_INFER BEGIN cached_recognizer' in block):
            self.update('正在识别', '录音完成，板端正在执行 ASR，请稍候。', None)
        asr_cache = list(re.finditer(rb'ASR_CACHE hit=(\d+) init_seconds=([0-9.]+)', data))
        if asr_cache:
            hit, seconds = asr_cache[-1].groups()
            cache_values = (hit, seconds)
            if cache_values != self.last_asr_cache:
                self.last_asr_cache = cache_values
                self.update('正在识别', '录音完成，板端正在执行 ASR，请稍候。',
                            f'ASR：缓存 {"hit" if hit == b"1" else "miss"} · 初始化 {float(seconds):.3f} 秒')
        statuses = list(re.finditer(
            rb'VOICE_PROVISION_STATUS phase=(\d+) state=(\d+) grammar=(\d+) '
            rb'turn=(\d+) candidates=(\d+) selected=(\d+) password_length=(\d+)', data))
        if statuses:
            values = tuple(map(int, statuses[-1].groups()))
            if values != self.last_status:
                self.last_status = values
                phase, state, grammar, turn, candidates, selected, length = values
                title, message = STATE_TEXT.get(state, ('板端处理中', '等待下一阶段状态。'))
                if phase == 2:
                    message += ' 现在正在录音。'
                elif phase == 3:
                    message = '录音结束，正在识别；请暂时保持安静。'
                extra = f'轮次 {turn} · 候选网络 {candidates} 个'
                if state in (3, 4):
                    extra += f' · 已输入 {length} 个密码字符'
                self.update(title, message, extra)


class Runner:
    def __init__(self, args, update):
        self.args = args
        self.update = update
        self.stop = threading.Event()

    def run(self):
        import serial
        self.args.logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        path = self.args.logs / ('spoken-panel-' + stamp + '.log')
        parser = ProgressParser(self.update)
        completed = False
        try:
            with path.open('xb') as log, serial.Serial(
                    self.args.port, 1500000, timeout=.04, write_timeout=2,
                    exclusive=True, rtscts=False, dsrdtr=False, xonxoff=False) as port:
                port.dtr = port.rts = False
                port.reset_input_buffer()
                port.write(b'\r')
                port.flush()
                time.sleep(.2)
                port.reset_input_buffer()
                self.update('正在启动完整测试', '板端将先播报联网提示。', None)
                port.write(b'k7voice flow-mic-provision\r')
                port.flush()
                end = time.monotonic() + self.args.timeout
                data = bytearray()
                while time.monotonic() < end:
                    block = port.read(8192)
                    if block:
                        data.extend(block)
                        log.write(block)
                        log.flush()
                        parser.feed(block)
                        final = re.findall(rb'VOICE_PROVISION phase=(\d+) turns=(\d+) error=(-?\d+)', data[-8192:])
                        if final:
                            phase, turns, error = map(int, final[-1])
                            completed = phase == 5 and error == 0
                            if completed:
                                self.update('联网成功', f'完整语音配网通过，共 {turns} 轮。', None)
                            else:
                                self.update('流程未通过', f'终止阶段 {phase}，错误码 {error}。', None)
                            break
                    if self.stop.is_set():
                        self.update('等待本轮安全结束', '停止已请求；当前语音或网络操作完成后释放串口。', None)
                    if len(data) > 16384:
                        del data[:-8192]
                else:
                    raise RuntimeError('完整语音配网测试超时。')
        except Exception as error:
            self.update('测试已暂停', str(error), None)
        finally:
            self.update(None, '日志：' + str(path), 'FINISHED_PASS' if completed else 'FINISHED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--timeout', type=int, default=660)
    parser.add_argument('--logs', type=Path, default=Path(__file__).resolve().parents[2] /
                        'evidence/spoken-panel-20260914')
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib, Gdk

    window = Gtk.Window(title='VelaVision · 完整语音配网测试')
    window.set_default_size(940, 620)
    window.set_border_width(30)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    window.add(box)
    header = Gtk.Label(label='板端 TTS → ASR → 扫网 → 选网 → 密码 → 联网')
    header.set_xalign(0)
    box.pack_start(header, False, False, 0)
    steps = Gtk.Label(label='①播报　②唤醒　③扫描　④选网　⑤密码　⑥连接')
    steps.set_name('steps')
    box.pack_start(steps, False, False, 0)
    status = Gtk.Label(label='等待板端固件就绪')
    status.set_name('status')
    status.set_line_wrap(True)
    box.pack_start(status, True, True, 0)
    detail = Gtk.Label(label='窗口会显示当前阶段；所有识别与联网操作都在 RK3576 板端执行。')
    detail.set_line_wrap(True)
    box.pack_start(detail, False, False, 0)
    metrics = Gtk.Label(label='诊断：—')
    metrics.set_name('metrics')
    metrics.set_line_wrap(True)
    box.pack_start(metrics, False, False, 0)
    buttons = Gtk.Box(spacing=16)
    start = Gtk.Button(label='开始完整语音配网测试')
    stop = Gtk.Button(label='停止（本轮结束后）')
    stop.set_sensitive(False)
    buttons.pack_start(start, True, True, 0)
    buttons.pack_start(stop, True, True, 0)
    box.pack_start(buttons, False, False, 0)
    footer = Gtk.Label(label='密码内容不会显示、不会写入日志。')
    footer.set_line_wrap(True)
    box.pack_start(footer, False, False, 0)
    css = Gtk.CssProvider()
    css.load_from_data(b'window {background:#f3f6fb;color:#172b45;} label {font-size:18px;} #steps {font-size:20px;font-weight:bold;color:#3564a8;} #status {font-size:34px;font-weight:bold;} #metrics {font-family:monospace;color:#294a70;} button {padding:18px;font-size:20px;}')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    active = [None]

    def render(state, message, info):
        if state:
            status.set_text(state)
        if info and info.startswith('FINISHED'):
            active[0] = None
            start.set_sensitive(not args.ready_file or args.ready_file.exists())
            stop.set_sensitive(False)
            footer.set_text(message)
        else:
            detail.set_text(message)
            if info:
                metrics.set_text('诊断：' + info)
        return False

    def readiness():
        ready = not args.ready_file or args.ready_file.exists()
        start.set_sensitive(ready and active[0] is None)
        if not ready and active[0] is None:
            status.set_text('正在准备板端固件')
            detail.set_text('等待 OTG RAM 加载、运行时验收和无线服务恢复。')
        elif ready and active[0] is None:
            status.set_text('可以开始测试')
            detail.set_text('点击开始后听板载语音，并按界面提示完成全流程。')
        return not ready

    def begin(_button):
        if active[0]:
            return
        runner = Runner(args, lambda *items: GLib.idle_add(render, *items))
        active[0] = runner
        start.set_sensitive(False)
        stop.set_sensitive(True)
        threading.Thread(target=runner.run, daemon=False).start()

    def request_stop(_button):
        if active[0]:
            active[0].stop.set()
            detail.set_text('已请求停止，等待当前板端操作安全结束。')

    def close(*_):
        if active[0]:
            request_stop(None)
            return True
        Gtk.main_quit()
        return False

    start.connect('clicked', begin)
    stop.connect('clicked', request_stop)
    window.connect('delete-event', close)
    window.show_all()
    if args.ready_file and readiness():
        GLib.timeout_add(1000, readiness)
    if args.snapshot:
        def take_snapshot():
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            pixbuf = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                                window.get_allocated_width(),
                                                window.get_allocated_height())
            if pixbuf:
                pixbuf.savev(str(args.snapshot), 'png', [], [])
            return False
        GLib.timeout_add(1000, take_snapshot)
    Gtk.main()


if __name__ == '__main__':
    main()
