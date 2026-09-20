"""Acquire fixed official Session source dependencies with ORT digest validation."""
import concurrent.futures,hashlib,json,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[1]
B=R/'work-in-progress/native-voice-sources'
locks=B/'onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/cmake/deps.txt'
out=B/'deps';out.mkdir(exist_ok=True)
selected={'utf8_range','protoc_linux_x64'}
rows=[line.split(';') for line in locks.read_text().splitlines() if line and not line.startswith('#')]
rows=[row for row in rows if row[0] in selected]
assert {row[0] for row in rows}==selected
def fetch(row):
 name,url,expected=row;target=out/(name+'.zip')
 try:
  if target.exists():data=target.read_bytes()
  else:
   fetch_url=url
   if '/archive/' in url:
    repo,rev=url[len('https://github.com/'):].split('/archive/',1)
    fetch_url='https://codeload.github.com/'+repo+'/zip/'+rev.removesuffix('.zip')
   with urllib.request.urlopen(fetch_url,timeout=60) as response:
    data=response.read(60*1024*1024+1)
  assert len(data)<=60*1024*1024
  assert hashlib.sha1(data).hexdigest()==expected,'Upstream SHA1 mismatch; refuse archive'
  if not target.exists():
   with target.open('xb') as stream:stream.write(data)
  info=dict(name=name,upstream_url=url,upstream_sha1=expected,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
   deps_file_sha256=hashlib.sha256(locks.read_bytes()).hexdigest(),compiled=False)
  target.with_suffix('.json').write_text(json.dumps(info,indent=2))
  print(name,len(data),'verified',flush=True)
  return info
 except Exception as error:
  print(name,str(error),flush=True);return dict(name=name,error=str(error))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,rows))
(out/'session-generator-fetch-results.json').write_text(json.dumps(results,indent=2))
if any('error' in row for row in results):raise SystemExit(1)
