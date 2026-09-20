"""Generate review-only patch; never modify project inputs."""
from pathlib import Path
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
paths = ['board/kickpi_k7/scripts/dramboot.ld',
         'board/kickpi_k7/src/kickpi_k7_appinit.c']
patch = []
inputs = {}
for path in paths:
    source = ROOT / path
    raw = source.read_bytes()
    inputs[path] = hashlib.sha256(raw).hexdigest()
    old = raw.decode().replace('\r\n', '\n')
    if path.endswith('.ld'):
        new = old.replace('    _sinit = ABSOLUTE(.);', '''    _sinit = ABSOLUTE(.);
    /* Runtime registration must precede every C++ initializer. */
    KEEP(*(.k7_unwind_init))''')
        new = new.replace('    *(.rodata .rodata.* .data.rel.ro .data.rel.ro.*)\n', '''    *(.rodata .rodata.* .data.rel.ro .data.rel.ro.*)
  } > dram :rodata

  .eh_frame ALIGN(8) : {
    __k7_eh_frame_start = .;
    KEEP(*(.eh_frame .eh_frame.*))
    /* libgcc walks until a zero-length record, not an end pointer. */
    LONG(0)
    __k7_eh_frame_end = .;
  } > dram :rodata

  .gcc_except_table ALIGN(8) : {
    __k7_lsda_start = .;
    KEEP(*(.gcc_except_table .gcc_except_table.*))
    __k7_lsda_end = .;
''')
        new = new.replace('.exitcall.exit .eh_frame)', '.exitcall.exit)')
    else:
        new = old.replace('/****************************************************************************\n * Public Functions', '''#if defined(CONFIG_CXX_EXCEPTION) && defined(CONFIG_BUILD_FLAT)
/* The flat image remains loaded for the entire boot.  Register exactly once
 * in lib_cxx_initialize(), after heap setup, before other constructors.
 * Do not move this into board_app_initialize(): that is too late.
 */
extern unsigned char __k7_eh_frame_start[];
extern void __register_frame(void *begin);

static void k7_unwind_initialize(void)
{
  static bool registered;

  if (!registered)
    {
      __register_frame(__k7_eh_frame_start);
      registered = true;
    }
}

/* A dedicated linker slot outranks all numeric init_array priorities.
 * This initializer is boot-serialized; the guard is not an SMP once API.
 */
static void (*const g_k7_unwind_init)(void)
  __attribute__((used, section(".k7_unwind_init"))) = k7_unwind_initialize;
#endif

/****************************************************************************
 * Public Functions''', 1)
        new = new.replace('#include <errno.h>', '#include <errno.h>\n#include <stdbool.h>')
    assert new != old
    (HERE / ('candidate-' + source.name)).write_text(new, encoding='utf-8')
    patch.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                    'a/' + path, 'b/' + path))
(HERE / 'candidate.patch').write_text(''.join(patch), encoding='utf-8')
(HERE / 'input-source-hashes.json').write_text(json.dumps(inputs, indent=2), encoding='utf-8')
