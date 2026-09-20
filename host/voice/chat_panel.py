"""Ubuntu test controls; openvela owns recording/reply loops. No auto recording."""
import argparse
import contextlib
import datetime
from pathlib import Path
import re
import threading
import time


class Status:
    def __init__(self):
        self.round = 0
        self.finished = False
        self.result = None

    def line(self, text):
        m = re.search(r'K7CLOUD chat listening round=(\d+)', text)
        if m:
            self.round = int(m[1])
            return '第 %d 轮 · 听短音后说话' % self.round, '麦克风准备完成才会响短音；音后说一句约 3 秒的短问题。'
        if 'SOUND cue frames=' in text:
            return '录音结束 · 正在完成识别', '可以停止说话，等待回答。'
        if 'K7CLOUD chat answering' in text:
            return '等待回答 · 下载与播放', '请听喇叭回答。服务异常时会说明原因；下一声短音后再说下一句。'
        m = re.search(r'K7CLOUD chat loop_done=(-?\d+)', text)
        if m:
            self.finished, self.result = True, int(m[1])
            if self.result == 0:
                return '本次测试已结束', '录音已停止。无声轮次也计入轮数；结束不代表每轮都有正确回答。'
            if self.result == -125:
                return '已停止', '板端已结束本次对话循环。'
            return '测试已暂停', '板端返回错误 %d，请检查日志；不会自动重新启动。' % self.result
        return None


class Runner:
    def __init__(self, args, update):
        self.args, self.update = args, update
        self.stop = threading.Event()
        self.started = False
        self.safe = True

    def run(self):
        import serial
        status = Status()
        self.args.logs.mkdir(parents=True, exist_ok=True)
        path = self.args.logs / ('chat-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.log')
        port = None
        try:
            port = serial.Serial(port=None, baudrate=1500000, timeout=.05,
                                 write_timeout=2, exclusive=True)
            port.dtr = port.rts = False
            port.port = self.args.port
            port.open()
            with contextlib.nullcontext(port):
                with path.open('x', encoding='utf-8') as log:
                    # A quiet prompt handshake before launching. No reset or camera access.
                    port.write(bytes([13]));port.flush()
                    data = bytearray();end = time.monotonic() + 3
                    while time.monotonic() < end:
                        data.extend(port.read(8192))
                        if b'nsh>' in data:break
                    if b'nsh>' not in data:
                        raise RuntimeError('未收到板端提示符，未启动录音。')
                    if self.stop.is_set():return
                    cmd = 'k7cloud chat-loop %s %d &' % (self.args.gateway, self.args.rounds)
                    # Once any command bytes may have been sent, require a terminal ACK.
                    self.safe = False
                    port.write(cmd.encode('ascii') + bytes([13]));port.flush()
                    self.started = True
                    buffer = b'';sent_stop = False;stop_deadline = None
                    deadline = time.monotonic() + self.args.rounds * 140 + 15
                    while not status.finished:
                        now = time.monotonic()
                        if (self.stop.is_set() or now > deadline) and not sent_stop:
                            port.write(b'k7cloud device-stop' + bytes([13]));port.flush()
                            sent_stop = True;stop_deadline = now + 25
                            self.update('正在停止', '等待板端确认停止，期间不能重新开始。')
                        if stop_deadline and now > stop_deadline:
                            raise RuntimeError('未收到停止确认，请检查串口；不能直接再次启动。')
                        buffer += port.read(8192)
                        if len(buffer) > 65536:
                            raise RuntimeError('串口输出异常，请检查板端。')
                        while b'\n' in buffer:
                            raw, buffer = buffer.split(b'\n', 1)
                            line = raw.decode('utf-8', 'replace')
                            event = status.line(line)
                            if event:
                                log.write(datetime.datetime.now().isoformat() + ' ' + line.strip() + '\n');log.flush()
                                self.update(*event)
                            if 'command not found' in line or 'usage: k7cloud' in line:
                                raise RuntimeError('板端不支持当前命令，请检查固件。')
                    self.safe = True
        except Exception as exc:
            self.update('测试已暂停', str(exc))
        finally:
            if port is not None and port.is_open:
                try:
                    if not self.safe:
                        port.write(b'k7cloud device-stop' + bytes([13]));port.flush()
                        tail = bytearray();end = time.monotonic() + 5
                        while time.monotonic() < end:
                            tail.extend(port.read(8192))
                            if re.search(rb'K7CLOUD chat loop_done=-?\d+',tail):
                                self.safe = True;break
                except Exception:
                    pass  # Unknown remains disabled; never claim a confirmed stop.
                finally:port.close()
            self.update(None, '日志：' + str(path), self.safe)


def main():
    import ipaddress
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', default='/dev/ttyUSB0')
    p.add_argument('--gateway', default='10.3.1.125')
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--logs', type=Path, default=Path(__file__).resolve().parents[2]/'evidence/chat-panel-20260915')
    p.add_argument('--snapshot', type=Path)
    args = p.parse_args()
    ipaddress.IPv4Address(args.gateway)
    if not 1 <= args.rounds <= 10:p.error('rounds must be 1..10')
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,GLib,Gdk
    window = Gtk.Window(title='VelaVision · 连续语音对话测试')
    window.set_default_size(900,500)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_border_width(30);window.add(box)
    title = Gtk.Label(label='板端录音 → 云端识别 → 后端回答 → 喇叭播放')
    box.pack_start(title,False,False,0)
    status = Gtk.Label(label='准备好后点击开始');status.set_name('status')
    box.pack_start(status,True,True,0)
    detail = Gtk.Label(label='每次听到短音后说一句短问题，等下一声短音再说下一句。')
    detail.set_line_wrap(True);box.pack_start(detail,False,False,0)
    buttons = Gtk.Box(spacing=18)
    start = Gtk.Button(label='开始 %d 轮对话' % args.rounds)
    stop = Gtk.Button(label='停止对话');stop.set_sensitive(False)
    buttons.pack_start(start,True,True,0);buttons.pack_start(stop,True,True,0)
    box.pack_start(buttons,False,False,0)
    footer = Gtk.Label(label='当前为无状态短句问答。窗口打开不会自动录音。')
    footer.set_line_wrap(True);box.pack_start(footer,False,False,0)
    css = Gtk.CssProvider()
    css.load_from_data(b'window{background:#f3f6fb;color:#172b45;} label{font-size:18px;} #status{font-size:32px;font-weight:bold;} button{font-size:20px;padding:18px;}')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    active = [None]
    def render(state,message,safe=None):
        if state:status.set_text(state);detail.set_text(message)
        if safe is not None:
            active[0] = None;stop.set_sensitive(False);start.set_sensitive(safe)
            footer.set_text(message + ('' if safe else '；状态未确认，已禁用重新开始。'))
        return False
    def begin(_):
        if active[0]:return
        runner = Runner(args,lambda *items:GLib.idle_add(render,*items))
        active[0] = runner;start.set_sensitive(False);stop.set_sensitive(True)
        status.set_text('正在连接板子');detail.set_text('请准备，听到短音后开始说话。')
        threading.Thread(target=runner.run,daemon=False).start()
    def request_stop(_):
        if active[0]:active[0].stop.set();stop.set_sensitive(False)
    def close(*_):
        if active[0]:request_stop(None);return True
        Gtk.main_quit();return False
    start.connect('clicked',begin);stop.connect('clicked',request_stop)
    window.connect('delete-event',close);window.show_all()
    if args.snapshot:
        def snapshot():
            pix=Gdk.pixbuf_get_from_window(window.get_window(),0,0,window.get_allocated_width(),window.get_allocated_height())
            if pix:args.snapshot.parent.mkdir(parents=True,exist_ok=True);pix.savev(str(args.snapshot),'png',[],[])
            return False
        GLib.timeout_add(700,snapshot)
    Gtk.main()

if __name__ == '__main__':main()
