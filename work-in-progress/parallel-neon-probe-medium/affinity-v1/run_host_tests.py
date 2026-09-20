import hashlib
import json
import pathlib
import subprocess
ROOT = pathlib.Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
LOCK = {
 'work-in-progress/parallel-llama-pool-safety/candidate/ggml-cpu.c': '24cdd4a9679ae2176468498075bc44ce39066474c2ac8f3ccb13141d6e452a67',
 'work-in-progress/parallel-llama-pool-safety/include/ggml-pool-safe.h': '1c318a45655a8fbd14dfe8393c142114510102a117f95a26e24a775a037ad775',
 'work-in-progress/parallel-llama-pool-safety/CONTRACT.md': '6ba3b0b7ab3962d259cb473276dddc5713719a7c4bf2175223ed85c2f607089f',
 'app/k7neon/k7neon_main.c': 'b2888ac37ba4d6ba9de0d78a1c5d3f4c7496fb3b433553b803c0fe3fffa215c4',
 'app/k7load/k7load_main.c': '43bcded686bcc34425b676a11077361ee871c37d1eee92b6653b8cc453b8f29a',
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for name, expected in LOCK.items():
    if sha(PROJECT / name) != expected: raise SystemExit('input changed: ' + name)
commands = [['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
             'affinity_gate.c', 'test_affinity.c', '-o', 'test-affinity.exe'],
            [str(ROOT / 'test-affinity.exe')]]
results = []
for command in commands:
    p = subprocess.run(command, cwd=str(ROOT), timeout=10, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True)
    results.append(dict(command=command, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
    if p.returncode: break
report = dict(scope='Mock callbacks only; NuttX adapter and pool not compiled or executed',
              passed=len(results)==2 and all(r['returncode']==0 for r in results), results=results)
(ROOT/'host-results.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
manifest = dict(inputs=LOCK, outputs={p.name:sha(p) for p in sorted(ROOT.iterdir())
                                     if p.is_file() and p.name!='hashes.json'})
(ROOT/'hashes.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['passed'] else 1)
