import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent
items={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(items,indent=2))
print('Sealed trace candidate + TRM additive review; prior host tests not rerun')
