from pathlib import Path
import json,zipfile,collections
p=Path(__file__).parent;r=json.loads((p/'tree-comparison.json').read_text());z=zipfile.ZipFile(p/'unaccepted-eigen.zip')
print('git modes',collections.Counter(x['mode'] for x in json.loads((p/'git-tree-manifest.json').read_text()).values()))
print('zip attrs',collections.Counter((x.create_system,oct(x.external_attr>>16),hex(x.external_attr&65535)) for x in z.infolist() if not x.is_dir()))
print('content mismatches',sum(1 for x in r['differences'] if x['git']['oid']!=x['zip']['oid']))
