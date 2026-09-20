"""Read-only 2h observer of the UI's single-owner telemetry. No serial access."""
import argparse,json,re,time
from pathlib import Path

def latest(rows,pattern):
    for row in reversed(rows):
        m=re.search(pattern,row.get('line',''))
        if m:return row,m
    return None,None

def assess(state,rows,now):
    problems=[]
    if now-state.get('sample_wall_time',0)>5:problems.append('stale_panel')
    for field in ('wifi','camera','video_fresh'):
        if not state.get(field):problems.append(field+'_not_ready')
    if state.get('serial_error'):problems.append('serial_error')
    age=state.get('network_age_s')
    if age is None or age>45:problems.append('network_reply_stale')
    b,bm=latest(rows,r'RADIO BLE name=.* connected=(\d+) handle=')
    h,hm=latest(rows,r'RADIO BLE history connections=(\d+) disconnections=(\d+) last_reason=(\d+) encrypt_status=(\d+) encrypted=(\d+)')
    m,mm=latest(rows,r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) Umem')
    for label,row in [('ble',b),('ble_history',h),('memory',m)]:
        if row is None or now-row['wall_time']>90:problems.append(label+'_stale')
    if bm and bm[1]!='1':problems.append('ble_disconnected')
    if hm and (hm[4]!='0' or hm[5]!='1'):problems.append('ble_not_encrypted')
    return {'problems':problems,'frames':state.get('frames',0),
            'heap_free':int(mm[3]) if mm else None,
            'ble_connections':int(hm[1]) if hm else None,
            'ble_disconnections':int(hm[2]) if hm else None}

def main():
    p=argparse.ArgumentParser();p.add_argument('--panel',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=7200)
    p.add_argument('--ready-timeout',type=int,default=900);a=p.parse_args()
    if not 60<=a.seconds<=7200:p.error('seconds must be 60..7200')
    a.output.mkdir(parents=True,exist_ok=False)
    baseline=None;start=None;waiting=time.monotonic();failures=[];samples=[];last_frame_change=waiting;previous_frames=None
    with (a.output/'samples.jsonl').open('x',encoding='utf-8') as sink:
        while True:
            now=time.time();mono=time.monotonic()
            try:
                state=json.loads((a.panel/'state.json').read_text())
                rows=[]
                if (a.panel/'telemetry.jsonl').exists():
                    for line in (a.panel/'telemetry.jsonl').read_text().splitlines():
                        try:rows.append(json.loads(line))
                        except ValueError:pass
                sample=assess(state,rows,now)
            except (OSError,ValueError):sample={'problems':['unreadable_state'],'frames':0,'heap_free':None}
            if sample['frames']!=previous_frames:last_frame_change=mono;previous_frames=sample['frames']
            if start is None and not sample['problems'] and mono-last_frame_change<5:
                baseline=sample.copy();start=mono
            if start is not None:
                if mono-last_frame_change>10:sample['problems'].append('video_frame_stalled')
                for key in ('ble_connections','ble_disconnections'):
                    if sample.get(key)!=baseline.get(key):sample['problems'].append(key+'_changed')
                if sample['frames']<baseline['frames']:sample['problems'].append('frame_counter_reset')
                if sample['problems']:failures.append({'elapsed':mono-start,'reasons':sample['problems']})
                samples.append(sample)
            elapsed=mono-start if start is not None else 0
            phase='running' if start is not None else 'waiting_for_baseline'
            if failures:phase='failed'
            elif start is not None and elapsed>=a.seconds:phase='completed_pending_memory_review'
            elif start is None and mono-waiting>=a.ready_timeout:phase='not_started'
            result={'phase':phase,'time':now,'elapsed_s':elapsed,'target_s':a.seconds,'sample':sample,'failures':failures,
                    'scope':'sampled connectivity/video; no end-to-end or independent internet claim'}
            heap=[x['heap_free'] for x in samples if x['heap_free'] is not None]
            if heap:result['memory']={'first':heap[0],'last':heap[-1],'min':min(heap),'max':max(heap),'delta':heap[-1]-heap[0]}
            sink.write(json.dumps(result)+'\n');sink.flush()
            tmp=a.output/'progress.tmp';tmp.write_text(json.dumps(result,indent=2));tmp.replace(a.output/'progress.json')
            if phase not in ('running','waiting_for_baseline'):break
            time.sleep(5)
    print(json.dumps(result))
if __name__=='__main__':main()
