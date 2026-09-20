import pathlib,json,re,statistics,csv
r=pathlib.Path(__file__).resolve().parents[1];suite=r/'evidence/suite-20260910T033126Z'
rows=[]
for d in sorted(suite.glob('memory-*')):
    result=json.loads((d/'result.json').read_text(encoding='utf8'));text=(d/'stdout.txt').read_text(encoding='utf8')
    marks={k:float(v) for k,v in re.findall(r'mark=(\w+) time=([\d.e+-]+)',text)}
    row={'label':d.name,'mode':d.name.rsplit('-',1)[0][7:],**{k:result[k] for k in ['peak_private','peak_working_set','os_peak_working_set','elapsed']},'marks':marks}
    for model in ['asr','tts']:
        if model+'_loaded' in marks:row[model+'_load_seconds']=marks[model+'_loaded']-marks[model+'_load_begin']
    outputs=[marks[k] for k in ['asr_first_nonempty','tts_first_complete_audio'] if k in marks]
    row['first_output_seconds']=min(outputs) if outputs else None
    samples=list(csv.DictReader((d/'memory.csv').open()))
    row['post_release_private_median']=statistics.median(int(s['private_bytes']) for s in samples[-5:])
    row['post_release_working_set_median']=statistics.median(int(s['working_set_bytes']) for s in samples[-5:])
    rows.append(row)
summary={}
for mode in ['asr','tts','both','sequential']:
    group=[x for x in rows if x['mode']==mode];summary[mode]={}
    for key in ['peak_private','peak_working_set','os_peak_working_set','asr_load_seconds','tts_load_seconds','first_output_seconds','post_release_private_median']:
        values=[x[key] for x in group if key in x]
        if values:summary[mode][key]={'min':min(values),'median':statistics.median(values),'max':max(values)}
(r/'evidence/memory-summary.json').write_text(json.dumps({'runs':rows,'summary':summary},indent=2))
lines=['| 方案（3个独立进程） | private峰值MiB 中位数 [最小,最大] | 工作集峰值MiB 中位数 [最小,最大] | ASR加载秒范围 | TTS加载秒范围 | 首次输出秒范围 |', '| --- | --- | --- | --- | --- | --- |']
def metric(x,scale=1):return f"{x['median']/scale:.1f} [{x['min']/scale:.1f}, {x['max']/scale:.1f}]"
def time_range(g,k):return f"{g[k]['min']:.3f}–{g[k]['max']:.3f}" if k in g else '—'
for mode,g in summary.items():lines.append('| '+mode+' | '+metric(g['peak_private'],2**20)+' | '+metric(g['peak_working_set'],2**20)+' | '+time_range(g,'asr_load_seconds')+' | '+time_range(g,'tts_load_seconds')+' | '+time_range(g,'first_output_seconds')+' |')
(r/'evidence/memory-table.md').write_text('\n'.join(lines)+'\n',encoding='utf8');print('\n'.join(lines))
