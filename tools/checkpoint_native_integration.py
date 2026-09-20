"""Record native integration without overwriting historical build identities."""
import json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
candidate=json.loads((ROOT/'evidence/native-photo-prompts-20260915/verification.json').read_text())
running=json.loads((ROOT/'evidence/device-intent-20260915/device-state.json').read_text())
manifest=ROOT/'project-manifest.json'
data=json.loads(manifest.read_text(encoding='utf-8'))
data['updated_at']=datetime.now(timezone.utc).isoformat()
data['whole_device_native_20260915']={
 'running_firmware_sha256':running['firmware_sha256'],
 'running_revision':'device-intent-20260915','boot':'RAM',
 'last_verified_wifi_ip':'10.3.0.214','stage_tts_user_confirmed':True,
 'camera_last_observation':'connected=0 committed=0; host start succeeded; capture not started',
 'candidate_revision':'native-photo-prompts-20260915',
 'candidate_sha256':candidate['sha256'],'candidate_build_exit_code':candidate['build_exit_code'],
 'candidate_loaded':False,'candidate_motion_tested':False,
 'candidate_features':['bounded exact three-view RAM retention','native command loop and cancellation',
                       'native photo progress prompts'],
 'photo_storage_durable':False,'backend_upload_verified':False,'chat_verified':False,
 'report_stream_verified':False,'multipart_encoder':'standalone tested source, not in firmware',
 'windows_bridge_pid':54580,'windows_bridge_echo_test':False,
 'server_speech':'stopped; backend owns key configuration',
 'handoff':'docs/整机无人值守软件推进_20260915.md'}
manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data['whole_device_native_20260915'],ensure_ascii=False))
