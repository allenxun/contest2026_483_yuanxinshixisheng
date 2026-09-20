import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print('pio.c SHA256 '+hashes['pio.c'])
