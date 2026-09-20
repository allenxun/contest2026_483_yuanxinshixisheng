"""Audit/apply this project's sources to its pinned external openvela SDK.

All destinations are checked before writing. Unknown SDK edits cause refusal.
Run --check for a read-only audit; --apply is explicit. No Git/board operations.
"""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--include', action='append', default=[],
                        help='sync only this exact project-relative file; repeatable')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true'); mode.add_argument('--apply', action='store_true')
    args=parser.parse_args(); sdk=args.sdk.resolve()
    inventory=json.loads((ROOT/'evidence/sdk-inventory.json').read_text(encoding='utf-8'))
    approved={x['source']:{x['sha256']} for x in inventory['files']}
    # Explicit hashes of locally generated, previously staged WPA sources.
    # This is sync provenance only, never evidence of a successful build.
    staging=ROOT/'evidence/sync/wifi-auth-20260909.json'
    if staging.exists():
        for path,digests in json.loads(staging.read_text(encoding='utf-8')).items():
            if not path.startswith('app/k7radio/'): raise RuntimeError('Unexpected staging scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).update(digests)
    # Explicit prior build evidence permits advancing known project edits.
    ip_staging=ROOT/'evidence/sync/wifi-ip-20260909.json'
    if ip_staging.exists():
        for path,digests in json.loads(ip_staging.read_text(encoding='utf-8')).items():
            if path.startswith('app/k7radio/'):
                rel='apps/examples/'+path[len('app/'):]
            elif path.startswith('board/kickpi_k7/configs/velavision_wifi_ip_local/'):
                rel='nuttx/boards/arm64/rk3576/'+path[len('board/'):]
            else: raise RuntimeError('Unexpected IP staging scope')
            approved.setdefault(rel,set()).update(digests)
    stability_baseline=ROOT/'evidence/sync/stability-session-20260917.json'
    if stability_baseline.exists():
        for path,digest in json.loads(stability_baseline.read_text()).items():
            if path != 'app/k7host/k7host_main.c':
                raise RuntimeError('Unexpected stability session scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    photo_lock_baseline=ROOT/'evidence/sync/photo-lock-retry-20260917.json'
    if photo_lock_baseline.exists():
        for path,digest in json.loads(photo_lock_baseline.read_text()).items():
            if path not in {'app/k7host/k7_pipeline.c','app/k7host/k7_photo.c','app/k7host/k7_photo.h'}:
                raise RuntimeError('Unexpected photo lock retry scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    report_follow_baseline=ROOT/'evidence/sync/report-follow-20260917.json'
    if report_follow_baseline.exists():
        for path,digest in json.loads(report_follow_baseline.read_text()).items():
            if path not in {'app/k7host/k7_pipeline.c','app/k7host/k7_pipeline.h','app/k7host/k7_photo.c','app/k7host/k7_photo.h','app/k7agent/cloud/src/board_speech_bridge.c'}:
                raise RuntimeError('Unexpected report follow scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    retry_baseline=ROOT/'evidence/sync/report-follow-attempt2-20260917.json'
    if retry_baseline.exists():
        for path,digest in json.loads(retry_baseline.read_text()).items():
            if path != 'app/k7agent/cloud/src/board_speech_bridge.c': raise RuntimeError('Unexpected follow retry scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    foreground_baseline=ROOT/'evidence/sync/photo-foreground-20260917.json'
    if foreground_baseline.exists():
        for path,digest in json.loads(foreground_baseline.read_text()).items():
            if path not in {'app/k7host/k7_pipeline.c','app/k7host/k7_photo_target.h'}:
                raise RuntimeError('Unexpected foreground scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    # Never approve the live destination itself or arbitrary directory contents.
    for revision in ('eapol-rx-20260909', 'credentials-20260909', 'phone-pairing-20260909', 'phone-rpa-20260909', 'wifi-auth-20260909', 'wifi-amsdu-index-20260909', 'ble-connect-20260909', 'wifi-arp-20260909'):
        previous=ROOT/f'evidence/build/{revision}/verification.json'
        if not previous.exists(): continue
        build=json.loads(previous.read_text(encoding='utf-8'))
        if build['build_exit_code']!=0: raise RuntimeError('Prior build was not successful')
        for path,digest in build['sources'].items():
            if path.startswith('app/k7radio/'):
                rel='apps/examples/'+path[len('app/'):]
                approved.setdefault(rel,set()).add(digest)
            elif path.startswith('port/tracked/nuttx/wireless/bluetooth/'):
                rel=path[len('port/tracked/'):]
                approved.setdefault(rel,set()).add(digest)
            elif path in ('board/kickpi_k7/configs/velavision_integrated_local/defconfig', 'board/kickpi_k7/configs/velavision_wifi_ip_local/defconfig'):
                rel='nuttx/boards/arm64/rk3576/'+path[len('board/'):]
                approved.setdefault(rel,set()).add(digest)
    # Exact model-arena build provenance for advancing the BSP mapping only.
    model_report=ROOT/'evidence/build/model-arena-20260910/verification.json'
    if model_report.exists():
        model=json.loads(model_report.read_text(encoding='utf-8'))
        if model['build_exit_code'] != 0: raise RuntimeError('Model arena build failed')
        path='port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c'
        approved.setdefault(path[len('port/new/'):],set()).add(model['sources'][path])
    emmc_report=ROOT/'evidence/build/emmc-readonly-20260910/verification.json'
    if emmc_report.exists():
        emmc=json.loads(emmc_report.read_text(encoding='utf-8'))
        if emmc['build_exit_code'] != 0: raise RuntimeError('eMMC build failed')
        for path,digest in emmc['sources'].items():
            if path.startswith('app/k7emmc/'):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    gpt_report=ROOT/'evidence/build/emmc-gpt-20260910/verification.json'
    if gpt_report.exists():
        gpt=json.loads(gpt_report.read_text(encoding='utf-8'))
        if gpt['build_exit_code'] != 0: raise RuntimeError('GPT build failed')
        for path,digest in gpt['sources'].items():
            if path.startswith('app/k7emmc/'):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    failed_stage=ROOT/'evidence/sync/emmc-block-attempt1.json'
    if failed_stage.exists():
        for path,digests in json.loads(failed_stage.read_text()).items():
            if path not in ('app/k7emmc/block_readonly.inc','app/k7emmc/test_block_readonly.c'):
                raise RuntimeError('Unexpected failed-stage scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).update(digests)
    # Pre-edit canonical K7 source hashes captured for the two-core diagnostic.
    smp_baseline=ROOT/'evidence/sync/smp-diag-baseline.json'
    if smp_baseline.exists():
        scope={'port/new/nuttx/arch/arm64/include/rk3576/chip.h',
               'port/new/nuttx/arch/arm64/include/rk3576/irq.h',
               'port/new/nuttx/arch/arm64/src/rk3576/Kconfig',
               'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c'}
        for path,digests in json.loads(smp_baseline.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected SMP baseline scope')
            approved.setdefault(path[len('port/new/'):],set()).update(digests)
    smp_prior=ROOT/'evidence/build/smp-reset-20260910/verification.json'
    if smp_prior.exists():
        previous=json.loads(smp_prior.read_text())
        if previous['build_exit_code'] != 0:raise RuntimeError('SMP prior build failed')
        for path,digest in previous['sources'].items():
            if path.startswith('app/k7smp/'):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    smp_four=ROOT/'evidence/build/smp-four-20260910/verification.json'
    if smp_four.exists():
        previous=json.loads(smp_four.read_text())
        if previous['build_exit_code'] != 0:raise RuntimeError('Four-core prior build failed')
        for path,digest in previous['sources'].items():
            if path.startswith('app/k7smp/'):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Failed service build provenance: only the exact pre-edit profile hash.
    service_stage=ROOT/'evidence/sync/smp-service-attempt1.json'
    if service_stage.exists():
        scope='board/kickpi_k7/configs/velavision_smp_service_local/defconfig'
        for path,digests in json.loads(service_stage.read_text()).items():
            if path != scope:raise RuntimeError('Unexpected SMP service staging scope')
            approved.setdefault('nuttx/boards/arm64/rk3576/'+path[len('board/'):],set()).update(digests)
    # Exact canonical pre-edit hashes of the reviewed unwind board changes.
    unwind_stage=ROOT/'evidence/sync/cxx-unwind-baseline.json'
    if unwind_stage.exists():
        scope={'board/kickpi_k7/scripts/dramboot.ld','board/kickpi_k7/src/kickpi_k7_appinit.c'}
        for path,digests in json.loads(unwind_stage.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected unwind staging scope')
            approved.setdefault('nuttx/boards/arm64/rk3576/'+path[len('board/'):],set()).update(digests)
    # Exact failed MSC build predecessor; only the reviewed class may advance.
    usb_stage=ROOT/'evidence/sync/usb-readonly-attempt1.json'
    if usb_stage.exists():
        for path,digests in json.loads(usb_stage.read_text()).items():
            if path != 'port/tracked/nuttx/drivers/usbhost/usbhost_storage.c':
                raise RuntimeError('Unexpected USB staging scope')
            approved.setdefault(path[len('port/tracked/'):],set()).update(digests)
    fat_stage=ROOT/'evidence/sync/fat-readonly-attempt1.json'
    if fat_stage.exists():
        for path,digests in json.loads(fat_stage.read_text()).items():
            if path != 'port/tracked/nuttx/fs/fat/fs_fat32dirent.c':
                raise RuntimeError('Unexpected FAT staging scope')
            approved.setdefault(path[len('port/tracked/'):],set()).update(digests)
    # This unified board profile was created after the initial SDK inventory.
    # Only completed audio I/O build provenance permits advancing its sources.
    audio_attempt=ROOT/'evidence/sync/audio-sound-attempt1.json'
    if audio_attempt.exists():
        for path,digests in json.loads(audio_attempt.read_text()).items():
            if path not in ('app/k7sound/i2c_owner.inc', 'app/k7sound/k7sound_main.c'):
                raise RuntimeError('Unexpected audio attempt scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).update(digests)
    for revision in ('audio-io-20260910', 'audio-sound-20260910', 'audio-fifo-20260910', 'audio-normal-20260910', 'audio-mic-20260910', 'audio-rxtrace-20260910', 'audio-reset-20260910', 'audio-gain-20260910', 'audio-input-20260910', 'audio-filter-20260910', 'audio-loopback-20260910', 'audio-route-20260910', 'audio-marker-20260910', 'audio-mmu-20260910', 'audio-rx2-20260910', 'audio-guard-20260910', 'audio-pause-20260911', 'audio-s16-20260911', 'audio-rde-20260911', 'audio-rx4-20260911', 'audio-mono-20260911', 'audio-grouped-attempt1-20260911'):
        previous=ROOT/'evidence/build'/revision/'verification.json'
        if previous.exists():
            report=json.loads(previous.read_text())
            if report['build_exit_code'] != 0: raise RuntimeError('Prior audio build failed')
            for path,digest in report['sources'].items():
                if path.startswith('app/k7audiohw/') or (revision in ('audio-sound-20260910', 'audio-fifo-20260910', 'audio-normal-20260910', 'audio-mic-20260910', 'audio-rxtrace-20260910', 'audio-reset-20260910', 'audio-gain-20260910', 'audio-input-20260910', 'audio-filter-20260910', 'audio-loopback-20260910', 'audio-route-20260910', 'audio-marker-20260910', 'audio-mmu-20260910', 'audio-rx2-20260910', 'audio-guard-20260910', 'audio-pause-20260911', 'audio-s16-20260911', 'audio-rde-20260911', 'audio-rx4-20260911', 'audio-mono-20260911', 'audio-grouped-attempt1-20260911') and path.startswith('app/k7sound/')):
                    approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Native voice integration advances only exact completed audio baseline hashes.
    voice_prior=ROOT/'evidence/build/audio-guard-20260910/verification.json'
    if voice_prior.exists():
        prior=json.loads(voice_prior.read_text())
        if prior['build_exit_code'] != 0: raise RuntimeError('Voice predecessor failed')
        profile='board/kickpi_k7/configs/velavision_audio_sound_local/defconfig'
        for path,digest in prior['sources'].items():
            if path.startswith('app/k7radio/'):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
            elif path==profile:
                approved.setdefault('nuttx/boards/arm64/rk3576/'+path[len('board/'):],set()).add(digest)
    shared_prior=ROOT/'evidence/build/voice-shared-20260910/verification.json'
    if shared_prior.exists():
        prior=json.loads(shared_prior.read_text())
        if prior['build_exit_code'] != 0: raise RuntimeError('Shared radio predecessor failed')
        for path,digest in prior['sources'].items():
            if path.startswith('app/k7radio/'):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
            elif path=='board/kickpi_k7/configs/velavision_audio_sound_local/defconfig':
                approved.setdefault('nuttx/boards/arm64/rk3576/'+path[len('board/'):],set()).add(digest)
    native_prior=ROOT/'evidence/build/voice-native-20260910/verification.json'
    if native_prior.exists():
        prior=json.loads(native_prior.read_text())
        if prior['build_exit_code'] != 0: raise RuntimeError('Native voice predecessor failed')
        for path,digest in prior['sources'].items():
            if path.startswith(('app/k7radio/','app/voicelink/')):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
            elif path=='board/kickpi_k7/configs/velavision_audio_sound_local/defconfig':
                approved.setdefault('nuttx/boards/arm64/rk3576/'+path[len('board/'):],set()).add(digest)
    cold_prior=ROOT/'evidence/build/voice-cold-20260910/verification.json'
    if cold_prior.exists():
        prior=json.loads(cold_prior.read_text())
        if prior['build_exit_code'] != 0: raise RuntimeError('Cold voice predecessor failed')
        for path,digest in prior['sources'].items():
            if path.startswith(('app/k7radio/','app/voicelink/')):
                approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    owner_attempt=ROOT/'evidence/sync/voice-owner-attempt1.json'
    if owner_attempt.exists():
        prior=json.loads(owner_attempt.read_text())
        path='app/k7radio/radio_backend.inc'
        approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(prior[path]['new'])
    voice_attempt=ROOT/'evidence/sync/voice-shared-attempt2.json'
    if voice_attempt.exists():
        scope={'wifi_scan.h','k7_radio_service.h','wifi_dispatch.h','wifi_scan.c',
               'radio_backend_state.inc','wifi_dispatch.c','radio_backend.inc',
               'prov_wifi.inc','prov_service.inc'}
        for path,digests in json.loads(voice_attempt.read_text()).items():
            if not path.startswith('app/k7radio/') or path[len('app/k7radio/'):] not in scope:
                raise RuntimeError('Unexpected native voice attempt scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).update(digests)
    # Exact reviewed ASR entry baseline; not arbitrary live SDK approval.
    asr_baseline=ROOT/'evidence/sync/asr-microphone-baseline.json'
    if asr_baseline.exists():
        for path,digest in json.loads(asr_baseline.read_text()).items():
            if path not in ('app/voicelink/CMakeLists.txt','app/voicelink/src/k7voice_main.cpp'):
                raise RuntimeError('Unexpected ASR baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Exact SDK predecessor for the reviewed password-confirmation gate.
    voice_confirmation=ROOT/'evidence/sync/voice-confirmation-baseline-20260912.json'
    if voice_confirmation.exists():
        scope={
            'app/voicelink/src/k7voice_main.cpp',
            'app/voicelink/include/voicelink/types.hpp',
            'app/voicelink/include/voicelink/parsers.hpp',
            'app/voicelink/include/voicelink/controller.hpp',
            'app/voicelink/src/parsers.cpp',
            'app/voicelink/src/core.cpp',
            'app/voicelink/src/voice_wifi_adapter.cpp',
            'app/voicelink/tests/test_flow.cpp',
            'app/voicelink/README.md',
        }
        for path,digest in json.loads(voice_confirmation.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected voice confirmation baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Completed confirmation-flow build is the exact predecessor of later
    # parser-only wake accommodations. This permits only its recorded source
    # hashes and does not approve arbitrary live SDK contents.
    confirmation_build=ROOT/'evidence/build/voice-flow-confirmation-20260912/verification.json'
    if confirmation_build.exists():
        prior=json.loads(confirmation_build.read_text())
        if prior['build_exit_code'] != 0: raise RuntimeError('Voice confirmation predecessor failed')
        scope={
            'app/voicelink/src/k7voice_main.cpp',
            'app/voicelink/include/voicelink/types.hpp',
            'app/voicelink/include/voicelink/parsers.hpp',
            'app/voicelink/include/voicelink/controller.hpp',
            'app/voicelink/src/parsers.cpp',
            'app/voicelink/src/core.cpp',
            'app/voicelink/src/voice_wifi_adapter.cpp',
            'app/voicelink/tests/test_flow.cpp',
            'app/voicelink/README.md',
        }
        for path,digest in prior['sources'].items():
            if path not in scope: raise RuntimeError('Unexpected voice confirmation build scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    flow_scan=ROOT/'evidence/sync/voice-flow-scan-baseline-20260912.json'
    if flow_scan.exists():
        scope={'app/voicelink/src/k7voice_main.cpp','app/voicelink/README.md'}
        for path,digest in json.loads(flow_scan.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected voice flow scan baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    asr_text=ROOT/'evidence/sync/voice-asr-text-baseline-20260912.json'
    if asr_text.exists():
        scope={'app/voicelink/CMakeLists.txt','app/voicelink/README.md',
               'app/voicelink/include/voicelink/asr_runtime.h',
               'app/voicelink/src/k7voice_main.cpp',
               'app/voicelink/src/native_asr_runtime.cpp'}
        for path,digest in json.loads(asr_text.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected ASR text bridge baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    voice_rule=ROOT/'evidence/sync/voice-rule-provision-baseline-20260912.json'
    if voice_rule.exists():
        scope={'app/voicelink/src/k7voice_main.cpp',
               'app/voicelink/CMakeLists.txt',
               'app/k7sound/k7sound_main.c'}
        for path,digest in json.loads(voice_rule.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected voice rule provisioning baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Exact SDK predecessor for the first formal DNS/HTTPS connectivity core.
    # New cloud files may be added, but only these three known k7agent files may
    # advance from their recorded pre-integration hashes.
    cloud_baseline=ROOT/'evidence/sync/k7cloud-baseline-20260912.json'
    if cloud_baseline.exists():
        scope={'app/k7agent/CMakeLists.txt','app/k7agent/Kconfig',
               'app/k7agent/README.md'}
        for path,digest in json.loads(cloud_baseline.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected k7cloud baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    mbedtls_baseline=ROOT/'evidence/sync/mbedtls-dtls-compat-baseline-20260912.json'
    if mbedtls_baseline.exists():
        scope={'port/tracked/apps/crypto/mbedtls/include/mbedtls/mbedtls_config.h',
               'port/tracked/apps/crypto/mbedtls/mbedtls/include/mbedtls/ssl.h'}
        for path,digest in json.loads(mbedtls_baseline.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected mbedTLS baseline scope')
            approved.setdefault(path[len('port/tracked/'):],set()).add(digest)
    mbedtls_attempt1=ROOT/'evidence/sync/mbedtls-dtls-compat-attempt1-20260912.json'
    if mbedtls_attempt1.exists():
        scope='port/tracked/apps/crypto/mbedtls/include/mbedtls/mbedtls_config.h'
        for path,digest in json.loads(mbedtls_attempt1.read_text()).items():
            if path != scope: raise RuntimeError('Unexpected mbedTLS attempt1 scope')
            approved.setdefault(path[len('port/tracked/'):],set()).add(digest)
    k7cloud_attempt3=ROOT/'evidence/sync/k7cloud-link-attempt3-20260913.json'
    if k7cloud_attempt3.exists():
        scope='app/k7agent/cloud/src/k7cloud_main.c'
        for path,digest in json.loads(k7cloud_attempt3.read_text()).items():
            if path != scope: raise RuntimeError('Unexpected k7cloud attempt3 scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    k7cloud_attempt4=ROOT/'evidence/sync/k7cloud-link-attempt4-20260913.json'
    if k7cloud_attempt4.exists():
        scope='app/k7agent/cloud/src/k7cloud_main.c'
        for path,digest in json.loads(k7cloud_attempt4.read_text()).items():
            if path != scope: raise RuntimeError('Unexpected k7cloud attempt4 scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Exact SDK predecessors captured before adding the offline cloud CLI
    # status commands. This permits only the two reviewed cloud files to
    # advance; it does not approve other live SDK differences.
    cloud_cli=ROOT/'evidence/sync/k7cloud-cli-baseline-20260914.json'
    if cloud_cli.exists():
        scope={'app/k7agent/CMakeLists.txt', 'app/k7agent/Kconfig',
               'app/k7agent/cloud/README.md',
               'app/k7agent/cloud/src/k7cloud_main.c'}
        for path,digests in json.loads(cloud_cli.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected cloud CLI baseline scope')
            if isinstance(digests, str): digests=[digests]
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).update(digests)
    pause_baseline=ROOT/'evidence/sync/audio-pause-baseline.json'
    if pause_baseline.exists():
        for path,digest in json.loads(pause_baseline.read_text()).items():
            if path not in ('app/k7sound/pio.c','app/k7sound/pio.h','app/k7sound/k7sound_main.c'):
                raise RuntimeError('Unexpected audio pause baseline scope')
            approved.setdefault('apps/examples/'+path[len('app/'):],set()).add(digest)
    # Accept only its recorded project snapshot, never the live SDK contents.
    board_profile='board/kickpi_k7/configs/velavision_integrated_local/defconfig'
    for item in json.loads((ROOT/'evidence/source-files.json').read_text(encoding='utf-8'))['files']:
        if item['path']==board_profile:
            rel='nuttx/boards/arm64/rk3576/kickpi_k7/configs/velavision_integrated_local/defconfig'
            approved.setdefault(rel,set()).add(item['sha256'])
    for repo, info in inventory['repositories'].items():
        actual=subprocess.check_output(['git','-C',str(sdk/repo),'rev-parse','HEAD'],text=True).strip()
        if actual!=info['head']: raise RuntimeError(f'{repo}: SDK HEAD differs from pinned baseline')
    radio_baseline=ROOT/'evidence/sync/cloud-radio-baseline-20260914.json'
    if radio_baseline.exists():
        scope={'app/k7agent/CMakeLists.txt','app/k7agent/Kconfig',
               'app/k7agent/cloud/src/k7cloud_main.c',
               'app/k7radio/k7_radio_service.h','app/k7radio/wifi_ip_service.inc',
               'board/kickpi_k7/configs/velavision_cloud_speech_local/defconfig'}
        for path,digest in json.loads(radio_baseline.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected cloud radio baseline scope')
            rel=('apps/examples/'+path[4:]) if path.startswith('app/') else ('nuttx/boards/arm64/rk3576/'+path[6:])
            approved.setdefault(rel,set()).add(digest)
    capture_baseline=ROOT/'evidence/sync/capture-stream-baseline-20260914.json'
    if capture_baseline.exists():
        scope={'app/k7sound/'+n for n in ('pio.c','pio.h','k7sound_main.c','CMakeLists.txt')}
        scope.update({'app/k7agent/CMakeLists.txt','app/k7agent/cloud/src/k7cloud_main.c'})
        for path,digest in json.loads(capture_baseline.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected capture stream baseline scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    bridge_baseline=ROOT/'evidence/sync/board-speech-bridge-20260914.json'
    if bridge_baseline.exists():
        scope={'app/k7agent/CMakeLists.txt','app/k7agent/cloud/src/k7cloud_main.c'}
        for path,digest in json.loads(bridge_baseline.read_text()).items():
            if path not in scope: raise RuntimeError('Unexpected board speech bridge scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    buffered_baseline=ROOT/'evidence/sync/board-speech-buffered-20260914.json'
    if buffered_baseline.exists():
        for path,digest in json.loads(buffered_baseline.read_text()).items():
            if path!='app/k7agent/cloud/src/board_speech_bridge.c':
                raise RuntimeError('Unexpected buffered speech scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    affinity_baseline=ROOT/'evidence/sync/board-speech-affinity-20260914.json'
    if affinity_baseline.exists():
        for path,digest in json.loads(affinity_baseline.read_text()).items():
            if path!='app/k7agent/cloud/src/board_speech_bridge.c':
                raise RuntimeError('Unexpected speech affinity scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    requested=set(args.include)
    pairs=[]
    for source, dest in [('app','apps/examples'), ('board/kickpi_k7','nuttx/boards/arm64/rk3576/kickpi_k7'),
                         ('port/new/nuttx','nuttx'), ('port/tracked/nuttx','nuttx'), ('port/tracked/apps','apps')]:
        for p in sorted((ROOT/source).rglob('*')):
            if p.is_file() and (not requested or p.relative_to(ROOT).as_posix() in requested):
                pairs.append((p, Path(dest)/p.relative_to(ROOT/source)))
    max_baseline=ROOT/'evidence/sync/tts-max-20260915.json'
    if max_baseline.exists():
        for path,digest in json.loads(max_baseline.read_text()).items():
            if path != 'app/k7sound/k7sound_main.c':raise RuntimeError('Unexpected TTS max baseline scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    found={p.relative_to(ROOT).as_posix() for p,_, in pairs}
    # Reviewed predecessor is the actually loaded photo-upload bridge.
    command_latency_baseline=ROOT/'evidence/sync/command-latency-20260917.json'
    if command_latency_baseline.exists():
        for path,digest in json.loads(command_latency_baseline.read_text()).items():
            if path not in {'app/k7sound/pio.c', 'app/k7agent/cloud/src/board_speech_bridge.c', 'app/k7agent/cloud/src/command_endpoint.h', 'app/k7sound/pio.h'}:raise RuntimeError('Unexpected command latency scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    side_yaw_baseline=ROOT/'evidence/sync/side-yaw13-20260917.json'
    if side_yaw_baseline.exists():
        for path,digest in json.loads(side_yaw_baseline.read_text()).items():
            if path not in {'app/k7host/fusion_core.h','app/k7host/fusion_core.c','app/k7host/k7_photo.c'}:raise RuntimeError('Unexpected side yaw scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    report_speech_baseline=ROOT/'evidence/sync/report-speech-20260917.json'
    if report_speech_baseline.exists():
        for path,digest in json.loads(report_speech_baseline.read_text()).items():
            if path not in {'app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/k7cloud_main.c'}:raise RuntimeError('Unexpected report speech scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    video_continuous_baseline=ROOT/'evidence/sync/video-continuous-20260917.json'
    if video_continuous_baseline.exists():
        for path,digest in json.loads(video_continuous_baseline.read_text()).items():
            if path != 'app/k7host/k7_link_probe.c':raise RuntimeError('Unexpected continuous video scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    photo_tcp_baseline=ROOT/'evidence/sync/photo-tcp-20260916.json'
    if photo_tcp_baseline.exists():
        for path,digest in json.loads(photo_tcp_baseline.read_text()).items():
            if path not in {'app/k7agent/cloud/src/board_speech_bridge.c','board/kickpi_k7/configs/velavision_photo_tcp/defconfig'}:
                raise RuntimeError('Unexpected photo TCP scope')
            target=('apps/examples/'+path[4:] if path.startswith('app/') else 'nuttx/boards/arm64/rk3576/'+path[6:])
            if digest is not None:approved.setdefault(target,set()).add(digest)
    photo_retry_baseline=ROOT/'evidence/sync/photo-retry-20260916.json'
    if photo_retry_baseline.exists():
        for path,digest in json.loads(photo_retry_baseline.read_text()).items():
            if path not in {'app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/k7cloud_main.c'}:
                raise RuntimeError('Unexpected photo retry scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    local_prompts_baseline=ROOT/'evidence/sync/local-prompts-20260916.json'
    if local_prompts_baseline.exists():
        for path,digest in json.loads(local_prompts_baseline.read_text()).items():
            if path not in {'app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/board_fixed_pcm.inc'}:
                raise RuntimeError('Unexpected local prompt scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    hello_baseline=ROOT/'evidence/sync/hello-keyword-20260916.json'
    if hello_baseline.exists():
        for path,digest in json.loads(hello_baseline.read_text()).items():
            if path not in {'app/k7agent/cloud/src/device_voice_intent.c','app/k7agent/cloud/src/board_voice_prompts.inc'}:
                raise RuntimeError('Unexpected hello keyword scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    keyword_baseline=ROOT/'evidence/sync/start-keyword-20260916.json'
    if keyword_baseline.exists():
        for path,digest in json.loads(keyword_baseline.read_text()).items():
            if path != 'app/k7agent/cloud/src/device_voice_intent.c':
                raise RuntimeError('Unexpected start keyword scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    backlog_baseline=ROOT/'evidence/sync/asr-backlog-20260916.json'
    if backlog_baseline.exists():
        for path,digest in json.loads(backlog_baseline.read_text()).items():
            if path not in {'app/k7sound/stream_ring.h','app/k7agent/cloud/src/board_speech_bridge.c'}:
                raise RuntimeError('Unexpected ASR backlog scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    skin_baseline=ROOT/'evidence/sync/skin-command-20260916.json'
    if skin_baseline.exists():
        expected={'app/k7agent/cloud/src/device_voice_intent.c':'12c7a78853386102e9976f60a782a019ac4c99bc67b2d948e210e03195a4bd6d',
                  'app/k7agent/cloud/src/board_voice_prompts.inc':'d0b73c9b6528ab96d0020d76fbe6c202328d7b2faf3665cc89266693a3e755a0'}
        recorded=json.loads(skin_baseline.read_text())
        if recorded != expected:raise RuntimeError('Unexpected skin command predecessor')
        for path,digest in recorded.items():
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    mono_baseline=ROOT/'evidence/sync/replay-mono-20260916.json'
    if mono_baseline.exists():
        expected={'app/k7sound/k7sound_main.c':'d2f06ba67528d10e007645c78eefc2d6c88e5232d4015632e579b41f29fdd76e',
                  'app/k7agent/cloud/src/device_voice_intent.c':'308b22bad89b6023a0a0446e53f60d7c79f847810dff0785c9daee774171b2b2'}
        recorded=json.loads(mono_baseline.read_text())
        if recorded != expected:raise RuntimeError('Unexpected replay mono predecessor')
        for path,digest in recorded.items():
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    replay_baseline=ROOT/'evidence/sync/replay-gain-20260916.json'
    if replay_baseline.exists():
        for path,digest in json.loads(replay_baseline.read_text()).items():
            if path != 'app/k7sound/k7sound_main.c' or digest != '49fd1130155a5db147a7ca1c7ac8b353f5c7fbd30d0a6eb8028cc11d6c451f42':
                raise RuntimeError('Unexpected replay gain predecessor')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    stage_watch_baseline=ROOT/'evidence/sync/stage-watch-20260916.json'
    if stage_watch_baseline.exists():
        for path,digest in json.loads(stage_watch_baseline.read_text()).items():
            if path != 'app/k7agent/cloud/src/board_speech_bridge.c' or digest != 'e4726340ae94628a245e0b421172398e87bcdbdf5515be471423910438a94337':
                raise RuntimeError('Unexpected stage watch predecessor')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    cue_baseline=ROOT/'evidence/sync/device-cue-20260915.json'
    if cue_baseline.exists():
        for path,digest in json.loads(cue_baseline.read_text()).items():
            if path != 'app/k7agent/cloud/src/board_speech_bridge.c' or digest != 'c415caa6579be2d01c8d021519c7b63eff6662afb564e27fc1a14d727e27245d':
                raise RuntimeError('Unexpected device cue predecessor')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    photo_upload_baseline=ROOT/'evidence/sync/photo-upload-20260915.json'
    if photo_upload_baseline.exists():
        for path,digest in json.loads(photo_upload_baseline.read_text()).items():
            if path != 'app/k7agent/cloud/src/board_speech_bridge.c':raise RuntimeError('Unexpected photo upload scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    photo_complete_baseline=ROOT/'evidence/sync/photo-complete-20260915.json'
    if photo_complete_baseline.exists():
        for path,digest in json.loads(photo_complete_baseline.read_text()).items():
            if path not in {'app/k7sound/k7sound_main.c','app/k7sound/pio.c','app/k7sound/pio.h','app/k7agent/cloud/src/board_speech_bridge.c','app/k7host/k7_pipeline.c'}:raise RuntimeError('Unexpected photo complete scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    timing_baseline=ROOT/'evidence/sync/speech-timing-20260915.json'
    if timing_baseline.exists():
        for path,digest in json.loads(timing_baseline.read_text()).items():
            if path not in {'app/k7sound/k7sound_main.c','app/k7sound/pio.c','app/k7sound/pio.h','app/k7agent/cloud/src/board_speech_bridge.c'}:raise RuntimeError('Unexpected speech timing scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    volume16_baseline=ROOT/'evidence/sync/speech-volume16-20260915.json'
    if volume16_baseline.exists():
        for path,digest in json.loads(volume16_baseline.read_text()).items():
            if path not in {'app/k7sound/k7sound_main.c','app/k7sound/codec_duplex.c'}:raise RuntimeError('Unexpected speech volume16 scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    volume_baseline=ROOT/'evidence/sync/speech-volume-20260915.json'
    if volume_baseline.exists():
        for path,digest in json.loads(volume_baseline.read_text()).items():
            if path != 'app/k7sound/k7sound_main.c':raise RuntimeError('Unexpected speech volume scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    cue_baseline=ROOT/'evidence/sync/native-chat-cue-20260915.json'
    if cue_baseline.exists():
        scope={'app/k7agent/cloud/src/board_speech_bridge.c','app/k7sound/k7sound_main.c','app/k7sound/capture_stream.h'}
        for path,digest in json.loads(cue_baseline.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected chat cue scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    chat_baseline=ROOT/'evidence/sync/native-chat-20260915.json'
    if chat_baseline.exists():
        scope={'app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/k7cloud_main.c'}
        for path,digest in json.loads(chat_baseline.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected native chat scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    coexist_baseline=ROOT/'evidence/sync/vision-ble-coexist-20260915.json'
    if coexist_baseline.exists():
        for path,digest in json.loads(coexist_baseline.read_text()).items():
            if path != 'app/k7host/k7_pipeline.c':raise RuntimeError('Unexpected vision coexist scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    reconnect_baseline=ROOT/'evidence/sync/camera-reconnect-20260915.json'
    if reconnect_baseline.exists():
        for path,digest in json.loads(reconnect_baseline.read_text()).items():
            if path != 'app/k7host/k7host_main.c':raise RuntimeError('Unexpected camera reconnect scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    prompts_baseline=ROOT/'evidence/sync/native-photo-prompts-20260915.json'
    if prompts_baseline.exists():
        scope={'app/k7host/'+p for p in ('k7_photo.c','k7_photo.h','k7_photo_store.c','k7_photo_store.h')}
        scope.update(('app/k7agent/CMakeLists.txt','app/k7agent/cloud/src/board_speech_bridge.c',
                      'app/k7agent/cloud/src/board_voice_prompts.inc','app/k7agent/cloud/src/device_photo_prompts.c',
                      'app/k7agent/cloud/include/device_photo_prompts.h'))
        for path,digest in json.loads(prompts_baseline.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected native photo prompts scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    loop_baseline=ROOT/'evidence/sync/device-loop-20260915.json'
    if loop_baseline.exists():
        scope={'app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/k7cloud_main.c'}
        for path,digest in json.loads(loop_baseline.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected device loop scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    photo_baseline=ROOT/'evidence/sync/native-photo-20260915.json'
    if photo_baseline.exists():
        scope={'app/k7host/'+p for p in ('CMakeLists.txt','k7_pipeline.c','k7_photo.c','k7_photo.h','k7_photo_store.c','k7_photo_store.h')}
        for path,digest in json.loads(photo_baseline.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected native photo scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    intent=ROOT/'evidence/sync/device-intent-20260915.json'
    if intent.exists():
        scope={'app/k7host/k7_pipeline.c','app/k7host/k7_pipeline.h','app/k7agent/CMakeLists.txt',
               'app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/k7cloud_main.c',
               'app/k7agent/cloud/src/device_voice_intent.c','app/k7agent/cloud/include/device_voice_intent.h'}
        for path,digest in json.loads(intent.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected device intent scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    stage=ROOT/'evidence/sync/voice-stage-20260915.json'
    if stage.exists():
        scope={'app/k7sound/'+p for p in ('pio.c','pio.h','k7sound_main.c','k7sound_api.h')}
        scope.update('app/k7agent/cloud/src/'+p for p in ('board_speech_bridge.c','k7cloud_main.c','board_voice_prompts.inc'))
        for path,digest in json.loads(stage.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected voice stage scope')
            if digest is not None:approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    voice_mode=ROOT/'evidence/sync/voice-mode-20260915.json'
    if voice_mode.exists():
        scope={'app/k7host/k7host_main.c','app/k7host/k7_pipeline.c',
               'app/k7host/k7_pipeline.h','app/k7host/k7_track.h'}
        for path,digest in json.loads(voice_mode.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected voice mode baseline scope')
            approved.setdefault('apps/examples/'+path[4:],set()).add(digest)
    missing=requested-found
    if missing: raise RuntimeError('Requested sync path is not mapped: '+', '.join(sorted(missing)))
    conflicts=[]; changes=[]
    for p, rel in pairs:
        target=(sdk/rel).resolve()
        # repo linkfile can point back into this same project, which is safe.
        if not target.is_relative_to(sdk) and not target.is_relative_to(ROOT.resolve()):
            conflicts.append(str(rel)+': target escapes SDK/project'); continue
        if target.exists() and sha(target)==sha(p): continue
        allowed=approved.get(rel.as_posix(),set())
        if target.exists() and sha(target) not in allowed:
            parts=rel.parts
            upstream=subprocess.run(['git','-C',str(sdk/parts[0]),'show','HEAD:'+Path(*parts[1:]).as_posix()],capture_output=True)
            if upstream.returncode or hashlib.sha256(upstream.stdout).hexdigest()!=sha(target):
                conflicts.append(str(rel)+': unknown local change'); continue
        changes.append((p,target,rel))
    if conflicts: raise RuntimeError('\n'.join(conflicts))
    if args.apply:
        for p,target,rel in changes:
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
    print(json.dumps(dict(result='PASS', source_files=len(pairs), changes=len(changes), applied=args.apply),ensure_ascii=False))

if __name__=='__main__': main()
