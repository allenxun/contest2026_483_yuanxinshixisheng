# Minimal NuttX logging ID candidate

Parent's real common target compile exposed SYS_gettid/SYS_getpid assumptions in ORT1.17.1 logging.cc. This candidate changes only three preprocessor sites under ORT_K7_NUTTX (the same common-target definition used by Env v2). Other platform branches remain unchanged.

* Exclude sys/syscall.h for ORT_K7_NUTTX.
* GetThreadId calls real gettid(), declared/implemented inline in frozen NuttX unistd.h:515–536. The implementation uses the current task/TLS thread ID; it is not a pthread pointer cast or invented ID.
* GetProcessId calls real getpid(), declared in the same header:369. No SYS_* ABI invocation or fabricated result. Exact process/task-group semantics are those of the linked NuttX implementation; this patch only supplies diagnostic IDs and does not assert Linux process isolation.

Full source and NuttX header frozen under input/, with original paths and SHA256 in inputs.json. Candidate logging.cc replaces only the matching frozen ORT common/logging/logging.cc in root's independent stage. Alternatively apply candidate.patch from ORT source root. No formal/SDK/device changes. Keep ORT_K7_NUTTX consistently defined for the common target; absent macro preserves upstream behavior. Recompile logging object and relink consumers rather than mixing stale objects.

No host mock was used and no target compilation is claimed here. Root owns the real ARM64 gate, already fixing date/include and staging include paths separately. This does not address fatal thread teardown or claim full ORT linking/runtime success.
