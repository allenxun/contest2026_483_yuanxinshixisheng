"""Ubuntu GTK control panel for real board wake/scan trials, never credentials."""
import argparse
import datetime
import os
from pathlib import Path
import re
import threading
import time
from manual_wifi import networks, Connector


def outcome(data):
    text = re.findall(rb'VOICE_FLOW wake_text=(.*?) bytes=\d+', data)
    state = re.findall(rb'VOICE_FLOW mic_state=(\d+) grammar=\d+ count=(\d+)', data)
    return (text[-1].decode('utf-8', 'replace') if text else '',
            bool(state and int(state[-1][0]) == 2 and int(state[-1][1]) > 0))


class Runner:
    def __init__(self, args, update):
        self.args, self.update = args, update
        self.stop = threading.Event()

    def command(self, port, log, command, timeout):
        port.write(command.encode('ascii') + b'\r')
        port.flush()
        data = bytearray()
        end = time.monotonic() + timeout
        last = time.monotonic()
        refreshed = False
        while time.monotonic() < end:
            block = port.read(8192)
            if block:
                data.extend(block)
                log.write(block)
                log.flush()
                last = time.monotonic()
            if re.search(rb'nsh>\s*(?:\x1b\[K)?\s*$', data):
                return bytes(data)
            completed = any(x in data for x in (b'SOUND result=', b'VOICE_FLOW mic_state=', b'VOICE_FLOW asr_error='))
            if completed and not refreshed and time.monotonic() - last > 2:
                port.write(b'\r')
                port.flush()
                refreshed = True
        raise RuntimeError('板端命令未按时结束；已停止自动重试，请检查串口。')

    def run(self):
        import serial
        self.args.logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        path = self.args.logs / ('wake-panel-' + stamp + '.log')
        try:
            with path.open('xb') as log, serial.Serial(
                    self.args.port, 1500000, timeout=.03, write_timeout=2,
                    exclusive=True, rtscts=False, dsrdtr=False, xonxoff=False) as port:
                port.dtr = port.rts = False
                self.command(port, log, '', 5)
                turn = 0
                while not self.stop.is_set():
                    turn += 1
                    for seconds in range(3, 0, -1):
                        self.update('准备 · %s 秒' % seconds,
                                    '第 %s 轮：请准备说“你好联网”' % turn, None)
                        if self.stop.wait(1):
                            break
                    if self.stop.is_set():
                        break
                    self.update('请连续说“你好联网”', '正在准备并录音，请持续说到界面变为“正在识别”。', None)
                    if not self.args.cued:
                        self.command(port, log, 'k7sound tone-max', 15)
                    capture = 'k7sound capture-cued 48000' if self.args.cued else 'k7sound capture-pga24-grouped 48000'
                    data = self.command(port, log, capture, 20)
                    if not re.search(rb'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0', data):
                        raise RuntimeError('录音结果不完整或失败，已停止；不会把旧录音当作本轮数据。')
                    if self.stop.is_set():
                        break
                    self.update('正在识别 · 请稍候', '可以暂停说话。板端通常需要约 30 秒；停止将在本轮安全结束后生效。', None)
                    result = self.command(port, log, 'k7voice flow-mic-wake', 210)
                    transcript, passed = outcome(result)
                    if passed:
                        aps = networks(result)
                        if not aps:
                            raise RuntimeError('唤醒通过，但网络列表输出不完整，请重新测试。')
                        self.update('请选择 Wi-Fi 并输入密码', '唤醒和扫网已通过；选择网络后点击连接。', transcript)
                        self.update(None, '选择网络并输入密码。', aps)
                        return
                    if not transcript and b'VOICE_FLOW asr_error=' not in result:
                        raise RuntimeError('识别结果串口输出不完整，暂停以免误判。')
                    self.update('本轮未通过 · 将自动重试', '识别内容：' + (transcript or '没有识别出文字'), transcript)
                    self.stop.wait(2)
                self.update('已停止', '串口已释放，可以重新开始。', None)
        except Exception as error:
            self.update('测试已暂停', str(error), None)
        finally:
            self.update(None, '日志：' + str(path), 'FINISHED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--cued', action='store_true', help='Only after capture-cued firmware is loaded')
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--logs', type=Path, default=Path(__file__).resolve().parents[2] / 'evidence/voice-panel-20260913')
    args = parser.parse_args()
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib, Gdk
    window = Gtk.Window(title='VelaVision · 板端语音唤醒测试')
    window.set_default_size(900, 520)
    window.set_border_width(32)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
    window.add(box)
    title = Gtk.Label(label='板端语音唤醒 / 真实 Wi-Fi 扫描')
    title.set_xalign(0)
    box.pack_start(title, False, False, 0)
    status = Gtk.Label(label='准备好了就点击开始')
    status.set_name('status')
    status.set_line_wrap(True)
    box.pack_start(status, True, True, 0)
    detail = Gtk.Label(label='开始后自动重复录音 → 板端识别 → 扫网，直到通过或你点击停止。\n只测试唤醒，不要说 Wi-Fi 密码。')
    detail.set_line_wrap(True)
    box.pack_start(detail, False, False, 0)
    recognized = Gtk.Label(label='最近识别：—')
    box.pack_start(recognized, False, False, 0)
    buttons = Gtk.Box(spacing=16)
    start = Gtk.Button(label='开始持续测试')
    stop = Gtk.Button(label='停止（本轮结束后）')
    stop.set_sensitive(False)
    buttons.pack_start(start, True, True, 0)
    buttons.pack_start(stop, True, True, 0)
    box.pack_start(buttons, False, False, 0)
    choices = Gtk.ComboBoxText()
    box.pack_start(choices, False, False, 0)
    password = Gtk.Entry()
    password.set_visibility(False)
    password.set_placeholder_text('Wi-Fi 密码（不记录到日志）')
    box.pack_start(password, False, False, 0)
    connect = Gtk.Button(label='连接所选 Wi-Fi')
    connect.set_sensitive(False)
    box.pack_start(connect, False, False, 0)
    footer = Gtk.Label(label='识别在 RK3576 上执行；通过以板端状态和扫描结果为准。')
    footer.set_line_wrap(True)
    box.pack_start(footer, False, False, 0)
    css = Gtk.CssProvider()
    css.load_from_data(b'window {background:#f3f6fb;color:#172b45;} label {font-size:19px;} #status {font-size:34px;font-weight:bold;} button {padding:18px;font-size:20px;}')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    active = [None]
    def readiness():
        if args.ready_file and not args.ready_file.exists():
            start.set_sensitive(False)
            status.set_text('正在准备板端固件')
            detail.set_text('窗口已就绪，等待 OTG 加载与无线服务恢复。完成后开始按钮会自动启用。')
            return True
        start.set_sensitive(True)
        status.set_text('准备好了就点击开始')
        detail.set_text('录音提示出现时可以连续说“你好联网”，直到进入识别阶段。不要说密码。')
        return False
    def render(state, message, text):
        if isinstance(text, list):
            choices.remove_all()
            for name in text:
                choices.append_text(name)
            choices.set_active(0)
        elif text == 'FINISHED':
            active[0] = None
            start.set_sensitive(True)
            stop.set_sensitive(False)
            connect.set_sensitive(choices.get_active_text() is not None)
            footer.set_text(message)
        else:
            if state:
                status.set_text(state)
            detail.set_text(message)
            if text is not None:
                recognized.set_text('最近识别：' + text)
        return False
    def begin(_button):
        if active[0]:
            return
        runner = Runner(args, lambda *items: GLib.idle_add(render, *items))
        active[0] = runner
        start.set_sensitive(False)
        connect.set_sensitive(False)
        choices.remove_all()
        stop.set_sensitive(True)
        threading.Thread(target=runner.run, daemon=False).start()
    def join(_button):
        if active[0] or choices.get_active_text() is None:
            return
        secret = password.get_text()
        if (secret and not 8 <= len(secret) <= 63) or any(ord(c) < 32 or ord(c) > 126 for c in secret):
            detail.set_text('密码需为 8–63 个可打印 ASCII 字符；开放网络可留空。')
            return
        worker = Connector(args, lambda *items: GLib.idle_add(render, *items), choices.get_active_text(), secret)
        password.set_text('')
        secret = None
        active[0] = worker
        start.set_sensitive(False)
        connect.set_sensitive(False)
        status.set_text('正在连接 Wi-Fi')
        detail.set_text('正在等待板端认证和 DHCP，请稍候。')
        threading.Thread(target=worker.run, daemon=False).start()
    def request_stop(_button):
        if active[0]:
            active[0].stop.set()
            detail.set_text('已请求停止，正在等待当前板端操作安全结束。')
    def close(*_):
        if active[0]:
            request_stop(None)
            return True
        Gtk.main_quit()
        return False
    start.connect('clicked', begin)
    stop.connect('clicked', request_stop)
    connect.connect('clicked', join)
    window.connect('delete-event', close)
    window.show_all()
    if args.ready_file and readiness():
        GLib.timeout_add(1000, readiness)
    if args.snapshot:
        def snapshot():
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            pixbuf = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                               window.get_allocated_width(), window.get_allocated_height())
            if pixbuf:
                pixbuf.savev(str(args.snapshot), 'png', [], [])
            return False
        GLib.timeout_add(1000, snapshot)
    Gtk.main()


if __name__ == '__main__':
    main()
