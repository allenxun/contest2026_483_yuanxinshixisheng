import json,datetime
from pathlib import Path
here=Path(__file__).resolve().parent;root=here.parents[1]
path=root/'project-manifest.json';data=json.loads(path.read_text())
data['updated_at']=datetime.datetime.now().astimezone().isoformat()
current=data['current_device']
current.update(revision='U-Boot Fastboot',state='TTS ROMFS and retained ASR CRC passed; waiting final OTG connection; application firmware not running',ram_booted=False,wifi_online=False,radio_host_online=False,wifi_shared_service_online=False,voice_wifi_provisioning_passed=False)
current['previous_manual_wifi_user_confirmed']=True
current['previous_manual_wifi_revision']='voice-ui-connect-20260913'
current['firmware_sha256']=None
current['dynamic_tts']=False
current['evidence']='docs/离线TTS语音配网接入_20260913.md'
data['pending_firmware']={'revision':'tts-spoken-flow-20260913','status':'build and ELF passed; ROMFS staged with CRC; final OTG transfer pending','sha256':'6ce956c4e9f755a22de8b3490f738def2fa18c3c34d4a2285982711d8c30a3b3','payload_sha256':'2bbb8a4861293b7b29818ddf22129bfb0fddb36012b4e8d2b89e5a65db5037ff','payload_bytes':116115184,'hardware_tested':False,'ram_boot_verified':False,'flash_commands':False,'evidence':'work-in-progress/tts-spoken-flow-20260913/'}
path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
