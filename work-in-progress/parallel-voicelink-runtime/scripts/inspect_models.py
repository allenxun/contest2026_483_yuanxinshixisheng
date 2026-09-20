import hashlib,json,pathlib,onnx,wave
root=pathlib.Path(__file__).resolve().parents[1]
models=pathlib.Path('E:/openvela/语音模块/openvela-voicelink/models')
asr=models/'sherpa-onnx-streaming-paraformer-bilingual-zh-en';tts=models/'vits-icefall-zh-aishell3'
selected=[asr/'encoder.int8.onnx',asr/'decoder.int8.onnx',asr/'tokens.txt',asr/'README.md',asr/'test_wavs/0.wav']+list(tts.iterdir())
records=[]
for p in selected:
    if not p.is_file():continue
    r={'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    if p.suffix=='.onnx':
        m=onnx.load(str(p),load_external_data=False)
        r['metadata']={v.key:v.value for v in m.metadata_props}
        r['opsets']=[{'domain':x.domain,'version':x.version} for x in m.opset_import]
        def tensor(v):
            t=v.type.tensor_type
            return {'name':v.name,'dtype':onnx.TensorProto.DataType.Name(t.elem_type),
                    'shape':[d.dim_param if d.dim_param else d.dim_value for d in t.shape.dim]}
        r['inputs']=[tensor(v) for v in m.graph.input];r['outputs']=[tensor(v) for v in m.graph.output]
        print(json.dumps(r,ensure_ascii=False,indent=2))
    if p.suffix=='.wav':
        with wave.open(str(p),'rb') as w:r['wav']={'rate':w.getframerate(),'channels':w.getnchannels(),'width':w.getsampwidth(),'frames':w.getnframes()}
    records.append(r)
(root/'evidence/models.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
