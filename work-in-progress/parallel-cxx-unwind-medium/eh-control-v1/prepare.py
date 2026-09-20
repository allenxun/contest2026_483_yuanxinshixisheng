"""Derive only a new control candidate from the immutable reviewed probe."""
from pathlib import Path
import difflib
import hashlib
import json
HERE=Path(__file__).resolve().parent
source=HERE.parent/'concurrent-probe-v1/k7eh_main.cxx'
raw=source.read_bytes()
digest=hashlib.sha256(raw).hexdigest()
assert digest=='667527d784ab9a80a7bc880a0c0d32818c051bc55c9949592edfec1bd6085536'
old=raw.decode('utf-8').replace('\r\n','\n')
new=old.replace('Explicit two-worker exception diagnostic. No peripheral or model access.',
                'Control diagnostic: single CPU5 cold, or complete preheat then CPU4/5.\n * Derived from concurrent-probe-v1; no peripheral or model access.')
new=new.replace('constexpr unsigned warm_rounds = 64;\n','')
new=new.replace('  int cpu = -1;','  int cpu = -1;\n  int requested_cpu = -1;')
new=new.replace('int(s.id + 4)','s.requested_cpu')
new=new.replace('CPU_SET(i + 4, &cpus);','CPU_SET(slots[i].requested_cpu, &cpus);')
new=new.replace('k7eh_main','k7ehcontrol_main')
new=new.replace('"cold"','"single"').replace('"warm"','"warm1"')
new=new.replace('usage: k7eh cold|warm (each needs a fresh boot; target CPUs 4 and 5)',
                'usage: k7ehcontrol single|warm1 (fresh boot each; single CPU5, warm1 CPU4/5)')
new=new.replace('  const unsigned rounds = warm ? warm_rounds : 1;',
                '  const unsigned rounds = 1;\n  const unsigned active = warm ? workers : 1;')
new=new.replace('rounds=%u workers=2 main_prethrow=%u\\n", argv[1], rounds, warm);',
                'rounds=%u workers=%u main_prethrow=%u\\n", argv[1], rounds, active, unsigned(warm));')
new=new.replace('    if (preheat.errors || preheat.caught != 1 || preheat.cleaned != 3) return 22;',
'''    if (preheat.errors || preheat.caught != 1 || preheat.cleaned != 3) {
      std::puts("K7EH PREHEAT_FAIL code=22 workers_created=0");
      return 22;
    }
    std::puts("K7EH PREHEAT_PASS caught=1 cleaned=3 workers_created=0");
    std::fflush(stdout);''')
new=new.replace('for (unsigned i = 0; i < workers; ++i) {',
                'for (unsigned i = 0; i < active; ++i) {')
new=new.replace('    slots[i].id = i;',
                '    slots[i].id = i;\n    slots[i].requested_cpu = warm ? int(i + 4) : 5;')
new=new.replace('created == workers','created == active').replace('reached(workers, r','reached(active, r')
new=new.replace('errors=%u cpu=%d cpu_mismatch=', 'errors=%u cpu=%d requested_cpu=%d cpu_mismatch=')
new=new.replace('i, s.caught, s.cleaned, s.errors, s.cpu, s.cpu_mismatches,',
                'i, s.caught, s.cleaned, s.errors, s.cpu, s.requested_cpu, s.cpu_mismatches,')
new=new.replace('K7EH ', 'K7EHCONTROL ')
(HERE/'k7ehcontrol_main.cxx').write_text(new,encoding='utf-8')
(HERE/'control-diff.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
    fromfile='concurrent-probe-v1/k7eh_main.cxx',tofile='eh-control-v1/k7ehcontrol_main.cxx')),encoding='utf-8')
(HERE/'input.json').write_text(json.dumps({'source':str(source),'sha256':digest,
    'changes':'single CPU5 worker versus full main preheat then two CPU4/5 workers; one round each',
    'source_unmodified':True},indent=2),encoding='utf-8')
