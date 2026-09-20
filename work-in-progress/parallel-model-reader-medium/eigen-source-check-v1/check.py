from pathlib import Path
import urllib.request,json,hashlib,zipfile,io,subprocess
p=Path(__file__).parent;sha='e7248b26a1ed53fa030c5c459f7ea095dfd276ac'
url=f'https://gitlab.com/libeigen/eigen/-/archive/{sha}/eigen-{sha}.zip'
with urllib.request.urlopen(url,timeout=30) as f:b=f.read(8*1024*1024+1)
assert len(b)<=8*1024*1024
(p/'unaccepted-eigen.zip').write_bytes(b)
z=zipfile.ZipFile(io.BytesIO(b));info={'url':url,'bytes':len(b),'sha1':hashlib.sha1(b).hexdigest(),'sha256':hashlib.sha256(b).hexdigest(),'expected_sha1':'be8be39fdbc6e60e94fa7870b280707069b5b81a','accepted':False,'entries':len(z.infolist()),'first_names':z.namelist()[:5],'zip_comment':z.comment.decode(errors='replace')}
(p/'archive.json').write_text(json.dumps(info,indent=2));print(json.dumps(info,indent=2))
url=f'https://gitlab.com/api/v4/projects/libeigen%2Feigen/repository/commits/{sha}'
try:
 with urllib.request.urlopen(url,timeout=20) as f:data=f.read(100000)
 (p/'official-commit.json').write_bytes(data);print(data.decode()[:1000])
except Exception as e:(p/'api-error.txt').write_text(str(e));print(e)
