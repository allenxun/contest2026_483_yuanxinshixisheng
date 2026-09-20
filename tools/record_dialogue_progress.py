import json,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
path=root/'project-manifest.json'
data=json.loads(path.read_text(encoding='utf-8-sig'))
out=root/'evidence/board-speech-affinity-20260914/manifest-before.json'
if not out.exists():out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
data['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
data['current_device'].update(revision='board-speech-buffered-20260914',
    state='Software rebooted into Fastboot for the authorized affinity repair. Waiting for VMware OTG attachment. Previous WiFi IP snapshot is invalid after reboot.',
    ram_booted=False,wifi_online=False,ble_online=False,ble_service_ready=False,
    radio_host_online=False,wifi_shared_service_online=False,ble_wifi_provisioning_available=False,
    cloud_speech_runtime_board_tested=True,
    evidence='evidence/board-speech-buffered-20260914/startup.log')
data['pending_firmware']={'revision':'board-speech-affinity-20260914','bytes':2791336,
    'sha256':'66659d8c865190dd936b28884fadc2c0c3411eeeb0507c61ee493ab9c7e2976e',
    'built':True,'loaded':False}
data['dialogue_progress']={'goal':'Real multi-turn K7 voice conversation through the specified business backend',
    'backend':'http://10.3.3.170:18085', 'direct_knowledgebase':False,
    'device_credentials_available':False,'backend_chat_contract_available':False,
    'cloud_tts_board_playback_user_confirmed':True,
    'asr_board_passed':False,'asr_last_failure':'buffered sender queued 51 frames then capture ring overflow; bridge received 0 complete frames',
    'same_c_sender_posix_test':{'frames':150,'completed':True,'audio':'synthetic silence'},
    'next':'Load affinity repair, provision WiFi, verify live ASR; obtain actual backend credentials/chat contract',
    'free_conversation_passed':False}
data['streaming_asr_gateway'].update(server='http://10.3.1.125:8000',
    board_bridge='tcp://10.3.1.125:8001',board_bridge_pid=54160)
path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
