from pathlib import Path
import hashlib,json
p=Path(__file__).parent;h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();r=Path('E:/openvela/VelaVision')
f=r/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/cmake/deps.txt';(p/'ort-deps.txt').write_bytes(f.read_bytes())
a=[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':h(f)} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ['outputs.json','delivery.json']]
(p/'outputs.json').write_text(json.dumps(a,indent=2));(p/'delivery.json').write_text(json.dumps({'status':'EXACT_COMMIT_TREE_VERIFIED_ORIGINAL_ARCHIVE_HASH_STILL_REJECTED','outputs_sha256':h(p/'outputs.json'),'tree_proof_sha256':h(p/'tree-proof.json')},indent=2))
for x in a:assert h(p/x['path'])==x['sha256']
for n in ['delivery.json','outputs.json','tree-proof.json']:print(n,h(p/n))
print('Verified',len(a),'files')
