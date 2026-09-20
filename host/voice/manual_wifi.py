"""Manual credentials over the board's echo-off input, never argv or raw logs."""
import ipaddress
import re
import threading
import time

def networks(data):
    names = []
    for value in re.findall(rb'VOICE AP ssid_hex=([0-9a-f]+)\r?\n', data):
        try:
            raw = bytes.fromhex(value.decode())
            name = raw.decode('utf-8')
            if 1 <= len(raw) <= 32 and not any(ord(c) < 32 for c in name) and name not in names:
                names.append(name)
        except (ValueError, UnicodeError):
            continue
    return names

def success_ip(data):
    match = re.search(rb'VOICE_UI connected ip=([0-9.]+)', data)
    if not match:
        return None
    try:
        address = ipaddress.IPv4Address(match[1].decode())
        if address.is_unspecified or address.is_loopback or address.is_multicast or address.is_link_local:
            return None
        return str(address)
    except ValueError:
        return None

class Connector:
    def __init__(self, args, update, ssid, password):
        self.args, self.update = args, update
        self.ssid, self.password = ssid, bytearray(password.encode('ascii'))
        self.stop = threading.Event()

    def run(self):
        import serial
        try:
            with serial.Serial(self.args.port, 1500000, timeout=.03, write_timeout=2,
                               exclusive=True, rtscts=False, dsrdtr=False, xonxoff=False) as port:
                port.dtr = port.rts = False
                port.write(b'\r')
                data = bytearray()
                end = time.monotonic() + 5
                while time.monotonic() < end and b'nsh>' not in data:
                    data.extend(port.read(4096))
                if b'nsh>' not in data:
                    raise RuntimeError('串口未就绪，未发送密码。')
                port.write(b'k7voice connect-ui\r')
                data.clear()
                end = time.monotonic() + 8
                while time.monotonic() < end and b'VOICE_UI INPUT_READY echo=off' not in data:
                    data.extend(port.read(4096))
                if b'VOICE_UI INPUT_READY echo=off' not in data:
                    raise RuntimeError('没有收到关闭回显确认，未发送密码。')
                # These bytes never pass through the regular command logger.
                port.write(self.ssid.encode('utf-8').hex().encode() + b'\n')
                port.write(self.password)
                port.write(b'\n')
                port.flush()
                for i in range(len(self.password)): self.password[i] = 0
                data.clear()
                end = time.monotonic() + 55
                while time.monotonic() < end:
                    data.extend(port.read(8192))
                    ip = success_ip(data)
                    if ip:
                        self.update('Wi-Fi 已连接', '板端真实 IP：' + ip + '。互联网/DNS/HTTPS 尚需另行验证。', None)
                        return
                    if b'VOICE_UI failed' in data:
                        raise RuntimeError('板端连接失败，请核对密码、信号和网络类型后重试。')
                    if len(data) > 131072:
                        del data[:-32768]
                raise RuntimeError('未收到真实 IP，连接尚未通过，请检查板端状态。')
        except Exception as error:
            self.update('连接未通过', str(error), None)
        finally:
            for i in range(len(self.password)): self.password[i] = 0
            self.update(None, '密码未写入日志或命令历史。', 'FINISHED')
