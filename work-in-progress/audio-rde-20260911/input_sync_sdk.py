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
    for revision in ('audio-io-20260910', 'audio-sound-20260910', 'audio-fifo-20260910', 'audio-normal-20260910', 'audio-mic-20260910', 'audio-rxtrace-20260910', 'audio-reset-20260910', 'audio-gain-20260910', 'audio-input-20260910', 'audio-filter-20260910', 'audio-loopback-20260910', 'audio-route-20260910', 'audio-marker-20260910', 'audio-mmu-20260910', 'audio-rx2-20260910', 'audio-guard-20260910', 'audio-pause-20260911'):
        previous=ROOT/'evidence/build'/revision/'verification.json'
        if previous.exists():
            report=json.loads(previous.read_text())
            if report['build_exit_code'] != 0: raise RuntimeError('Prior audio build failed')
            for path,digest in report['sources'].items():
                if path.startswith('app/k7audiohw/') or (revision in ('audio-sound-20260910', 'audio-fifo-20260910', 'audio-normal-20260910', 'audio-mic-20260910', 'audio-rxtrace-20260910', 'audio-reset-20260910', 'audio-gain-20260910', 'audio-input-20260910', 'audio-filter-20260910', 'audio-loopback-20260910', 'audio-route-20260910', 'audio-marker-20260910', 'audio-mmu-20260910', 'audio-rx2-20260910', 'audio-guard-20260910', 'audio-pause-20260911') and path.startswith('app/k7sound/')):
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
    pairs=[]
    for source, dest in [('app','apps/examples'), ('board/kickpi_k7','nuttx/boards/arm64/rk3576/kickpi_k7'),
                         ('port/new/nuttx','nuttx'), ('port/tracked/nuttx','nuttx'), ('port/tracked/apps','apps')]:
        for p in sorted((ROOT/source).rglob('*')):
            if p.is_file(): pairs.append((p, Path(dest)/p.relative_to(ROOT/source)))
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
