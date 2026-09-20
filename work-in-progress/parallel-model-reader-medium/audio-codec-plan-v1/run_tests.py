import pathlib,re,json,subprocess,hashlib
R=pathlib.Path(__file__).resolve().parent; P=R.parents[2]
K=P/'work-in-progress/parallel-k7-codec'; A=P/'work-in-progress/parallel-k7-audio'
(R/'evidence').mkdir(exist_ok=True)
src=K/'input/kernel-6.1/sound/soc/codecs/es8323.c'; s=src.read_text()
fields=[
 ('left_differential',0x0a,0xc0,0xc0,'es8323_left_dac_enum, ES8323_ADCCONTROL2, 6, 3'),
 ('right_differential',0x0a,0x30,0x30,'es8323_right_dac_enum, ES8323_ADCCONTROL2, 4, 3'),
 ('differential_line2',0x0b,0x80,0x80,'es8323_diff_enum, ES8323_ADCCONTROL3, 7'),
 ('stereo_mux',0x0b,0x18,0,'es8323_mono_enum, ES8323_ADCCONTROL3, 3'),
 ('capture_mute_on',0x0f,4,4,'SOC_SINGLE("Capture Mute", ES8323_ADCCONTROL7, 2, 1, 0)'),
 ('capture_mute_off',0x0f,4,0,'SOC_SINGLE("Capture Mute", ES8323_ADCCONTROL7, 2, 1, 0)'),
 ('adc_s16',0x0c,0x1c,0x0c,'adciface |= 0x000C'),
 ('dac_s16',0x17,0x38,0x18,'daciface |= 0x0018'),
]
records=[];checks=0
for name,reg,mask,value,anchor in fields:
 assert anchor in s
 assert value & ~mask == 0
 for old in range(256):
  new=(old&~mask)|value
  assert new&mask==value and new&~mask==old&~mask
  checks+=1
 records.append(dict(name=name,reg=reg,field_mask=mask,field_value=value,source=src.relative_to(P).as_posix(),source_line=s[:s.index(anchor)].count('\n')+1,evidence='REFERENCE_ONLY',hardware_readback_allowed=False))
assert '{4096000, 16000, 256, 0x2, 0x0}' in s
assert 16000*256==4096000 and 16000*2*16==512000
assert '"Left Right", "Left Left", "Right Right", "Right Left"' in s
assert '0, 1, 3' in s
assert '"Line 1", "Line 2"' in s
(R/'reference-fields.json').write_text(json.dumps({'executable_plan':False,'reviews':0,'hardware_read_rules':[],'fields':records,'clock_reference':{'rate':16000,'mclk':4096000,'sr':2,'usb':0,'adc_reg':13,'dac_reg':24,'slot_profile_unmeasured':[2,16],'bclk_request':512000}},indent=2)+'\n')
# Preserve complete source bodies, including branches/delays, instead of inventing a flattened order.
def body(name):
 m=re.search(r'static int '+name+r'\([^;]*?\n\{',s); assert m,name
 i=m.end();level=1
 while level:
  level+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[m.start():i]
(R/'reference-sequences.txt').write_text('\n\n'.join(body(n) for n in ['es8323_reset','es8323_set_dai_fmt','es8323_pcm_hw_params','es8323_mute','es8323_set_bias_level','es8323_probe']))
paths=[src,K/'input/kernel-6.1/sound/soc/codecs/es8323.h',K/'input/kernel-6.1/arch/arm64/boot/dts/rockchip/rk3576-kickpi-k7.dtsi',K/'input/sources.json',K/'include/codec_txn.h',K/'src/codec_txn.c',K/'tests/test_codec.c',K/'HANDOFF.md',K/'PROVENANCE.md',K/'CONTRACT.md',A/'HARDWARE.md',A/'sources/K7_V2.0_20250716_SCH-p32.txt',A/'sources/K7_V1.1_20241211_SCH-p32.txt',A/'sources/K7_V2.0_20250716_SCH-p33.txt']
(R/'evidence/inputs.json').write_text(json.dumps([{'path':p.relative_to(P).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],indent=2)+'\n')
results=[{'check':'Reference field algebra against all 256 old byte values; not hardware RMW or readback authorization','checks':checks,'passed':True}]
gcc=r'D:\software\mingw64\mingw64\bin\gcc.exe'
for cmd,timeout in [([gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','-I'+str(K/'include'),str(K/'src/codec_txn.c'),str(K/'tests/test_codec.c'),'-o',str(R/'evidence/engine-tests.exe')],30),([str(R/'evidence/engine-tests.exe')],15)]:
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 results.append(dict(command=cmd,timeout_seconds=timeout,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
 (R/'evidence/results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(r.stdout,r.stderr,end='')
 assert r.returncode==0
