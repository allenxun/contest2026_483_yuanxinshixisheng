"""Ubuntu integration console. Board owns vision, commands, photos and upload."""
import argparse,datetime,json,queue,re,sys,threading,time,subprocess
import math
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
from track_overlay import BOX, TRACK, display_box

class State:
    def __init__(self):
        self.wifi=False; self.network_stamp=0; self.camera=False; self.probed=False; self.busy=False; self.single=False; self.done=0
        self.status='连接设备后，先查看视频'; self.command='尚未识别'
        self.pose='等待姿态数据'; self.upload='尚未上传'; self.held=True
        self.recovery_started=0
        self.pending_box=None;self.telemetry={}
        self.pose_stamp=0;self.pose_guidance='等待板端姿态数据'
        self.pose_sequence=None
        self.hold_confirm_pending=False
        self.report_task=''
    def line(self,s):
        box=BOX.search(s)
        if box:
            q,x,y,w,h,edge=box.groups();values=[float(v) for v in (x,y,w,h)]
            if all(math.isfinite(v) for v in values) and 0<=values[0]<160 and 0<=values[1]<120 and 0<values[2]<=160 and 0<values[3]<=120:
                self.pending_box=dict(sequence=int(q),box=values,edge=int(edge))
        track=TRACK.search(s)
        if track:
            q,st,dx,dy,x,y,tx,age=track.groups()
            record=dict(sequence=int(q),state=int(st),received_at=time.monotonic())
            if self.pending_box and self.pending_box['sequence']==int(q):record.update(self.pending_box)
            self.telemetry=record
            if self.hold_confirm_pending and int(st)==4:
                self.hold_confirm_pending=False;self.camera=True;self.held=True
                self.status='相机待命 · 板端已确认停止模式'
        if 'UVC probe result=' in s:
            self.probed='result=0 committed=1' in s
            if not self.probed:self.status='相机协商失败 · 请查看日志'
        m=re.search(r'K7CLOUD radio_generation=\d+ wifi=([01]) ipv4_ready=([01])\b',s)
        if m:
            self.wifi=m[1]=='1' and m[2]=='1';self.network_stamp=time.monotonic()
            if self.recovery_started:
                self.recovery_started=0;self.status='控制通道已恢复' if self.wifi else '控制通道已恢复 · Wi-Fi 未就绪'
        if re.search(r'UVC STREAM .*elapsed_ms=\d+.*result=-?\d+',s):
            self.hold_confirm_pending=False
            self.camera=False;self.status='相机采集已结束 · 本次启动不能重复采集'
        if 'VOICE SESSION ready mode=0' in s:
            self.camera=True; self.held=True; self.status='相机待命 · 云台停止'
        if 'K7CLOUD device round=' in s or 'k7cloud asr-live ' in s:
            self.busy=True; self.status='等待短音 · 音后说话'
        if 'SOUND cue frames=' in s:self.status='录音已结束 · 正在识别'
        m=re.search(r'K7CLOUD device intent=(\d+)',s)
        if m:self.command={0:'未匹配命令',1:'启动云台',2:'皮肤检测',3:'停止云台',4:'停止播报'}.get(int(m[1]),'未知命令')
        m=re.search(r'VOICE MODE applied=(\d+) result=(-?\d+)',s)
        if m and int(m[2])==0 and int(m[1]) in (0,1,2):
            self.camera=True
            self.held=int(m[1])==0
            self.status={0:'云台已停止',1:'人脸跟随中',2:'三角度拍摄中'}.get(int(m[1]),'模式已改变')
            if int(m[1])==2:self.done=0; self.upload='尚未上传'
        m=re.search(r'VOICE MODE requested=0 result=(-?\d+)\b',s)
        if m:self.hold_confirm_pending=m[1]=='0'
        m=re.search(r'POSE .*?y=([-\d.]+) p=([-\d.]+) r=([-\d.]+).*?done=(\d+)',s)
        if m:
            self.pose='偏航 %s° · 俯仰 %s° · 横滚 %s°'%tuple(m.group(i) for i in (1,2,3));self.done=int(m[4]);self.pose_stamp=time.monotonic()
            sequence=re.search(r'POSE q=(\d+)\b',s)
            self.pose_sequence=int(sequence[1]) if sequence else None
            phase=re.search(r'v=(\d+) st=(\d+) next=(\d+)',s)
            if phase:
                valid,reason,nxt=map(int,phase.groups())
                self.pose_guidance={1:'请正对镜头，保持片刻',2:'请向自己的左侧转头',4:'请向自己的右侧转头'}.get(nxt,'等待板端拍摄状态')
                if not valid:self.pose_guidance='等待目标人脸完整入镜和有效角度'
                elif abs(float(m[2]))>12 or abs(float(m[3]))>12:self.pose_guidance='请平视镜头，减少抬头、低头或歪头'
                if not valid:self.pose='本帧角度不可用'
                if reason==6:
                    self.pose_guidance='目标锁定未就绪，请保持单人入镜'
                if self.done==7:self.pose_guidance='三角度已采集，等待上传结果'
        quality=re.search(r'POSEQ q=(\d+).*?lost=([01])\b',s)
        if quality and int(quality[1])==self.pose_sequence and quality[2]=='1':
            self.pose='目标锁定已丢失'
            self.pose_guidance=('本组三图已中断；回正后说“皮肤检测”重新拍摄'
                                if self.done else '请单人正对镜头，等待重新锁定')
        if 'PHOTO complete ' in s:self.done=7;self.status='三张已采集 · 等待停止和上传'
        m=re.search(r'K7CLOUD photo_upload .*?result=(-?\d+) accepted=(\d+)',s)
        if m:self.upload='后端已受理（不代表分析完成）' if m[1]=='0' and m[2]=='1' else '上传未获受理，请查看日志'
        m=re.search(r'K7CLOUD photo_upload .*accepted=1 task=([0-9a-f-]{36})',s)
        if m:self.report_task=m[1]
        if 'K7CLOUD report_started ' in s:
            self.busy=True;self.status='正在读取后端报告并分段播报'
        if 'K7CLOUD report_status ' in s:
            self.upload='报告状态已返回 · 等待分段播放'
        m=re.search(r'K7CLOUD report_segment played=(\d+)',s)
        if m:self.status='报告已播放 '+m[1]+' 段'
        m=re.search(r'K7CLOUD report_done result=(-?\d+) segments=(\d+)',s)
        if m:
            self.busy=False
            self.status='报告分段播放完成' if m[1]=='0' else '报告播放中止 · 请查看日志'
            self.upload='后端已受理 · 报告已播完' if m[1]=='0' else '报告播放未完成 · 可重新播放'
            task=re.search(r'task=([0-9a-f-]{36})',s)
            if task:self.report_task=task[1]
        m=re.search(r'K7CLOUD photo_retry result=(-?\d+) retained_views=(\d+)',s)
        if m:
            self.busy=False;self.done=int(m[2])
            self.status='照片重传已获受理' if m[1]=='0' else '照片重传失败 · 保留原图，请查看日志'
        # Concurrent UART prefixes can interleave; the native terminal field
        # remains intact (observed "device stoce loop_done=-125").
        if re.search(r'\bloop_done=-?\d+\b',s):self.busy=False
        m=re.search(r'K7CLOUD asr result=(-?\d+) frames_sent=(\d+) completed=([01])',s)
        if m and self.single:
            self.busy=False;self.single=False
            self.status=('单次语音识别完成' if m[1]=='0' and m[3]=='1'
                         else '单次语音识别失败 · 请查看诊断结果')
        if 'K7CLOUD timing asr_completed_us=' in s:
            self.status='识别结束 · 等待命令处理'
            if self.single:self.busy=False;self.single=False;self.status='单次语音检查结束'

class Board:
    def __init__(self,args,state,log):
        self.args=args;self.state=state;self.log=log;self.commands=queue.Queue()
        self.quit=threading.Event();self.port=None;self.error='';self.capture_attempted=False;self.capture_sent=False
        self.capture_started=0;self.ready_check_sent=False
    def send(self,cmd):self.commands.put(cmd)
    def run(self):
        import serial
        try:
            p=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2,exclusive=True)
            p.dtr=False;p.rts=False;p.port=self.args.port;p.open();self.port=p
            buffer=b'';next_send=0
            while not self.quit.is_set():
                try:
                    if time.monotonic()<next_send:raise queue.Empty
                    cmd=self.commands.get_nowait()
                    for byte in (cmd+'\r').encode():p.write(bytes([byte]));p.flush();time.sleep(.004)
                    next_send=time.monotonic()+2
                    self.log.write(('\nCOMMAND '+cmd+'\n').encode())
                except queue.Empty:pass
                raw=p.read(min(p.in_waiting or 1,16384))
                if not raw:continue
                self.log.write(raw);buffer+=raw
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    text=line.decode(errors='replace')
                    self.state.line(text)
                    if getattr(self.args,'soak_telemetry',False):
                        if re.search(r'^(?:RADIO BLE (?:name=|history |disconnected |connection status=)|K7CLOUD (?:radio_generation=|timing |endpoint |prompt_started|photo_|report_)|VOICE MODE |UVC STREAM |\s*\d+(?:\s+\d+){6} Umem)',text):
                            with (self.args.output/'telemetry.jsonl').open('a',encoding='utf-8') as sink:
                                sink.write(json.dumps({'wall_time':time.time(),'monotonic':time.monotonic(),'line':text},ensure_ascii=False)+'\n')
                if len(buffer)>65536:buffer=b''
        except Exception as e:self.error=str(e);self.state.camera=False;self.state.wifi=False
        finally:
            if self.port:
                try:self.port.write(b'k7cloud device-stop\rk7host halt\r');self.port.flush()
                except Exception:pass
                self.port.close();self.port=None

class Video:
    def __init__(self):
        self.jpeg=None;self.frame=None;self.stamp=0;self.frames=0;self.error='等待 USB 视频设备';self.stop=threading.Event();self.arrivals=deque(maxlen=120)
    def fps(self):
        arrivals=list(self.arrivals)
        return (len(arrivals)-1)/(arrivals[-1]-arrivals[0]) if len(arrivals)>1 and arrivals[-1]>arrivals[0] else 0
    def run(self):
        import usb.core,usb.util
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
        from k7_video_receiver import Receiver
        rx=Receiver()
        while not self.stop.is_set():
            dev=None;claimed=False
            try:
                dev=usb.core.find(idVendor=0x1209,idProduct=0x0001)
                if dev is None:self.stop.wait(.5);continue
                # VID/PID is the stable probe identity. Avoid a product-string
                # control transfer here: during VMware disconnect/re-enumeration
                # it can block inside libusb and freeze the GTK main loop.
                try: dev.default_timeout=200
                except Exception: pass
                cfg=dev.get_active_configuration();ep=usb.util.find_descriptor(cfg[(0,0)],bEndpointAddress=0x81)
                if ep is None or ep.wMaxPacketSize!=512:raise RuntimeError('USB视频端点不符')
                usb.util.claim_interface(dev,0);claimed=True;self.error='已接入 · 等待相机图像'
                while not self.stop.is_set():
                    try:raw=bytes(dev.read(0x81,16384,timeout=200))
                    except usb.core.USBTimeoutError:rx.expire();continue
                    frame=rx.feed(raw)
                    if frame:
                        self.jpeg=frame['jpeg'];self.stamp=time.monotonic();self.frames+=1;self.error='';self.arrivals.append(self.stamp);self.frame=frame
            except Exception as e:self.error='USB视频：'+str(e);self.stop.wait(1)
            finally:
                rx.reset();self.jpeg=None;self.frame=None;self.stamp=0;self.arrivals.clear()
                if dev:
                    if claimed:
                        try:usb.util.release_interface(dev,0)
                        except Exception:pass
                    usb.util.dispose_resources(dev)

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='/dev/ttyUSB0');p.add_argument('--gateway',default='10.3.1.125');p.add_argument('--device-ip',default='10.3.0.214')
    p.add_argument('--soak-telemetry',action='store_true')
    p.add_argument('--report-task',default='')
    p.add_argument('--camera-seconds',type=int,choices=range(1,10801),metavar='1..10800',default=1800)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--connect',action='store_true');p.add_argument('--attach',action='store_true');p.add_argument('--confirmed-camera',action='store_true');p.add_argument('--resume-camera',action='store_true');a=p.parse_args()
    if a.report_task:
        import uuid
        a.report_task=str(uuid.UUID(a.report_task))
    import ipaddress;ipaddress.IPv4Address(a.gateway)
    sys.path.append('/usr/lib/python3/dist-packages')
    sys.path.append('/home/swl/openvela/work/rk3576-bringup/host-tools/root/usr/lib/python3/dist-packages')
    import gi;gi.require_version('Gtk','3.0');gi.require_foreign('cairo')
    from gi.repository import Gtk,GLib,Gdk,GdkPixbuf
    a.output.mkdir(parents=True,exist_ok=True)
    log=(a.output/('console-'+datetime.datetime.now().strftime('%H%M%S')+'.log')).open('ab',buffering=0)
    state=State();board=Board(a,state,log);video=Video()
    state.report_task=a.report_task
    if a.resume_camera:
        state.probed=True;board.capture_attempted=True;board.capture_sent=True
        board.capture_started=time.monotonic()
        state.status='正在接回预览 · 等待板端停止模式确认'
    win=Gtk.Window(title='VelaVision · 整机联调');win.set_default_size(1100,700)
    root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);root.set_border_width(20);win.add(root)
    title=Gtk.Label(label='实时预览 · 语音控制 · 三角度拍摄 · 后端上传');root.pack_start(title,False,False,0)
    row=Gtk.Box(spacing=20);root.pack_start(row,True,True,0)
    image=Gtk.DrawingArea();image.set_size_request(640,480);row.pack_start(image,True,True,0)
    render_state={'pixbuf':None,'sequence':0,'frames':0,'arrivals':deque(maxlen=120)}
    mirror=Gtk.CheckButton(label='镜像预览（与旧版一致，仅改变显示）');mirror.set_active(True);root.pack_start(mirror,False,False,0)
    def draw_image(widget,cr):
        pix=render_state['pixbuf']
        if pix is None:return False
        scale=min(widget.get_allocated_width()/640,widget.get_allocated_height()/480)
        cr.save();cr.translate((widget.get_allocated_width()-640*scale)/2,(widget.get_allocated_height()-480*scale)/2);cr.scale(scale,scale)
        Gdk.cairo_set_source_pixbuf(cr,pix,0,0);cr.paint()
        box=display_box(state.telemetry,render_state['sequence'],time.monotonic(),mirror.get_active())
        if box:
            (x1,y1),(x2,y2)=box;cr.set_source_rgb(0,1,0);cr.set_line_width(2);cr.rectangle(x1,y1,x2-x1,y2-y1);cr.stroke()
        cr.restore();return False
    image.connect('draw',draw_image)
    sidebar=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18);row.pack_start(sidebar,False,False,0)
    labels={}
    for key in ['connection','status','command','pose','photos','upload','video']:
        label=Gtk.Label();label.set_xalign(0);label.set_line_wrap(True);label.set_width_chars(26);label.set_max_width_chars(30)
        sidebar.pack_start(label,False,False,0);labels[key]=label
    confirm=Gtk.CheckButton(label='已复位到 0/0、周围无遮挡，允许真实语音控制');root.pack_start(confirm,False,False,0)
    controls=Gtk.Box(spacing=12);root.pack_start(controls,False,False,0)
    buttons={}
    for key,label in [('connect','连接设备'),('camera','相机待命'),('asr','单次语音检查'),('voice','开始语音整机测试'),('stop','停止录音与云台')]:
        b=Gtk.Button(label=label);controls.pack_start(b,True,True,0);buttons[key]=b
    foot=Gtk.Label(label='打开窗口不自动录音或运动。听短音后说“你好 OpenVela”或“开始测肤”。');foot.set_line_wrap(True);root.pack_start(foot,False,False,0)
    root.reorder_child(controls,1);root.reorder_child(confirm,2);root.reorder_child(foot,3)
    if a.resume_camera:confirm.set_active(True)
    def connect(_):
        if board.port or board.error:return
        threading.Thread(target=board.run,daemon=True).start();threading.Thread(target=video.run,daemon=True).start()
        board.send('k7cloud radio-status')
        if not a.attach:board.send('k7host start');board.send('k7host linkvideo &')
        buttons['connect'].set_sensitive(False)
    def camera(_):
        if not confirm.get_active() or not board.port or board.capture_attempted:return
        board.capture_attempted=True;state.status='相机启动中 · 初始保持停止'
        board.send('k7host probe')
    def voice(_):
        if not (confirm.get_active() and state.camera and state.wifi and not state.busy and time.monotonic()-video.stamp<3):return
        state.busy=True;board.send('k7cloud device-loop '+a.gateway+' 60 &')
    def stop(_):
        if board.port:board.send('k7cloud device-stop');board.send('k7host halt');state.status='已请求停止 · 等待板端确认'
    def asr(_):
        if not board.port or not state.wifi or state.busy:return
        state.single=True;state.busy=True;state.status='单次检查 · 短音后说皮肤检测'
        board.send('k7cloud asr-live '+a.gateway+' &')
    buttons['connect'].connect('clicked',connect);buttons['camera'].connect('clicked',camera)
    buttons['voice'].connect('clicked',voice);buttons['stop'].connect('clicked',stop)
    buttons['asr'].connect('clicked',asr)
    recovery=Gtk.Button(label='恢复控制通道 / 刷新联网状态');root.pack_start(recovery,False,False,0)
    def recover(_):
        if not board.port or state.busy:return
        board.send('\x03\x15');board.send('k7cloud radio-status')
        state.recovery_started=time.monotonic()
        state.status='正在恢复控制通道 · 不录音、不运动'
    recovery.connect('clicked',recover)
    retry=Gtk.Button(label='重传已拍三图（不重拍）');root.pack_start(retry,False,False,0)
    def retry_photos(_):
        if not (board.port and state.wifi and state.done==7 and state.held and not state.busy):return
        state.busy=True;state.status='正在重传保留的三张照片'
        board.send('k7cloud photo-retry '+a.gateway+' &')
    retry.connect('clicked',retry_photos)
    report_button=Gtk.Button(label='播放皮肤检测报告');root.pack_start(report_button,False,False,0)
    def play_report(_):
        if not (board.port and state.wifi and state.held and not state.busy and state.report_task):return
        state.busy=True;state.status='正在请求报告流 · 不启动相机或云台'
        board.send('k7cloud report-play '+a.gateway+' '+state.report_task+' &')
    report_button.connect('clicked',play_report)
    seen=[None];closing=[False];poll=[0];health_poll=[0]
    def render():
        frame=video.frame
        fresh=frame is not None and time.monotonic()-frame['received_at']<3
        if not fresh:
            if render_state['pixbuf'] is not None:render_state['pixbuf']=None;image.queue_draw()
            return True
        key=(frame['sequence'],frame['received_at'],mirror.get_active())
        if seen[0]!=key:
            try:
                loader=GdkPixbuf.PixbufLoader.new_with_type('jpeg');loader.write(frame['jpeg']);loader.close();pix=loader.get_pixbuf()
                if pix.get_width()!=640 or pix.get_height()!=480:raise ValueError('unexpected video dimensions')
                render_state['pixbuf']=pix.flip(True) if mirror.get_active() else pix
                render_state['sequence']=frame['sequence'];render_state['frames']+=1;render_state['arrivals'].append(time.monotonic());seen[0]=key
            except Exception:video.error='JPEG解码失败';render_state['pixbuf']=None
        image.queue_draw();return True
    def tick():
        fresh=video.stamp and time.monotonic()-video.stamp<3
        if state.recovery_started and time.monotonic()-state.recovery_started>10:
            state.recovery_started=0;state.status='恢复超时 · 板端未响应控制命令'
        labels['connection'].set_text('串口：'+('故障 '+board.error if board.error else '已连接' if board.port else '未连接')+'\nWi-Fi：'+('在线' if state.wifi else '待确认'))
        labels['status'].set_text(state.status);labels['command'].set_text('匹配命令：'+state.command)
        labels['pose'].set_text((state.pose+'\n'+state.pose_guidance) if state.pose_stamp and time.monotonic()-state.pose_stamp<1 else '等待新的板端姿态数据')
        labels['photos'].set_text('三角度：'+' / '.join(n+(' ✓' if state.done & b else ' ○') for n,b in [('正面',1),('左侧',2),('右侧',4)]))
        labels['upload'].set_text(state.upload)
        times=list(render_state['arrivals']);display_fps=(len(times)-1)/(times[-1]-times[0]) if len(times)>1 and times[-1]>times[0] else 0
        labels['video'].set_text(('640×480 · 接收 %.1f / 显示 %.1f FPS\n%d 帧'%(video.fps(),display_fps,video.frames)) if fresh else (video.error or '视频已过期，等待新帧'))
        buttons['camera'].set_sensitive(bool(board.port and confirm.get_active() and not board.capture_attempted))
        buttons['asr'].set_sensitive(bool(board.port and state.wifi and not state.busy and not closing[0]))
        buttons['voice'].set_sensitive(bool(board.port and state.camera and state.wifi and confirm.get_active() and fresh and not state.busy and not closing[0]))
        recovery.set_sensitive(bool(board.port and not state.busy and not closing[0]))
        retry.set_sensitive(bool(board.port and state.wifi and state.done==7 and state.held and not state.busy and not closing[0]))
        report_button.set_sensitive(bool(board.port and state.wifi and state.held and not state.busy and state.report_task and not closing[0]))
        # Keep the network indicator sourced from the board's radio-status
        # line.  A synchronous ping here can block GTK during VMware routing
        # hiccups and was the cause of the apparent frozen panel.
        if board.port and not state.wifi:
            foot.set_text('语音按钮暂不可用：尚未收到板端联网确认。可点击下方“恢复控制通道”。')
        else:
            foot.set_text('听短音后说“你好 OpenVela”或“开始测肤”。单次语音检查不会驱动云台。')
        if board.port and state.wifi and not state.camera:
            foot.set_text('等待板端相机就绪确认；收到确认后开放整机测试。' if not board.ready_check_sent else '正在核对相机停止模式；请稍候，勿重复启动相机。')
        if closing[0] and state.held and not state.busy:
            board.quit.set();video.stop.set();Gtk.main_quit();return False
        if board.port and (not state.busy or a.soak_telemetry) and time.monotonic()-poll[0]>15:
            board.send('k7cloud radio-status');poll[0]=time.monotonic()
        if a.soak_telemetry and board.port and time.monotonic()-health_poll[0]>60:
            for cmd in ('k7radio ble-status','free'):board.send(cmd)
            health_poll[0]=time.monotonic()
        (a.output/'state.tmp').write_text(json.dumps({'sample_wall_time':time.time(),'network_age_s':time.monotonic()-state.network_stamp if state.network_stamp else None,'status':state.status,'wifi':state.wifi,'camera':state.camera,'busy':state.busy,'held':state.held,'voice_enabled':buttons['voice'].get_sensitive(),'video_fresh':bool(fresh),'video_error':video.error,'serial_error':board.error,'frames':video.frames,'done':state.done,'upload':state.upload},ensure_ascii=False))
        (a.output/'state.tmp').replace(a.output/'state.json')
        if a.confirmed_camera and board.port and state.wifi and not board.capture_attempted:
            a.confirmed_camera=False;confirm.set_active(True);camera(None)
        if board.capture_attempted and state.probed and not board.capture_sent:
            board.capture_sent=True;board.capture_started=time.monotonic();board.send('k7host voicecam %d &' % a.camera_seconds)
        # The one-shot SESSION line can be lost amid concurrent UART output.
        # Same-mode HOLD does not increment native revision or print APPLIED.
        # An accepted HOLD followed by fresh TRACK_HALTED also confirms readiness.
        if (board.port and board.capture_sent and fresh and not state.camera
                and not state.busy and not board.ready_check_sent
                and time.monotonic()-board.capture_started>5):
            board.ready_check_sent=True;board.send('k7host voicemode hold')
        # If the board's confirmation line is lost in a busy TRACK stream,
        # fresh video proves the preview path is alive. Keep the device in the
        # safe held state and re-enable voice controls instead of leaving the
        # UI stuck forever.
        if (board.capture_sent and fresh and state.wifi and not state.camera
                and not state.busy and time.monotonic()-board.capture_started>8):
            state.camera=True;state.held=True
            state.status='相机待命 · 已由实时视频确认停止模式'
        if (a.resume_camera and board.capture_sent and fresh and state.wifi
                and state.held and time.monotonic()-board.capture_started>3):
            state.busy=False;state.camera=True
            state.status='相机待命 · 云台停止，可进行语音控制'
        return True
    def close(*_):
        if board.port and (state.busy or not state.held):closing[0]=True;stop(None);return True
        board.quit.set();video.stop.set();Gtk.main_quit();return False
    css=Gtk.CssProvider();css.load_from_data(b'window{background:#f3f6fb;color:#172b45;} label{font-size:18px;} button{padding:12px;font-size:16px;}')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    win.connect('delete-event',close);win.show_all();GLib.timeout_add(200,tick);GLib.timeout_add(33,render)
    def snapshot():
        pix=Gdk.pixbuf_get_from_window(win.get_window(),0,0,win.get_allocated_width(),win.get_allocated_height())
        if pix:pix.savev(str(a.output/'panel.png'),'png',[],[])
        return False
    if a.connect:GLib.idle_add(lambda: (connect(None),False)[1])
    GLib.timeout_add(1200,snapshot);Gtk.main()

if __name__=='__main__':main()
