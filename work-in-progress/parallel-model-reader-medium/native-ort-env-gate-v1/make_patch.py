from pathlib import Path
import difflib
p=Path(__file__).parent;s=(p/'input/00-ort-env.txt').read_text();old=s
for h in ['dlfcn.h','ftw.h','sys/mman.h','sys/syscall.h']:
 s=s.replace('#include <'+h+'>','#if !defined(ORT_K7_NUTTX)\n#include <'+h+'>\n#endif')
s=s.replace('#include <unistd.h>','#include <unistd.h>\n#if defined(ORT_K7_NUTTX)\n#include <nuttx/config.h>\n#include <pthread.h>\n#include <time.h>\nstatic_assert(sizeof(off_t) >= 8, "ORT K7 requires 64-bit off_t");\n#endif')
s=s.replace('&& !defined(_AIX)', '&& !defined(_AIX) && !defined(ORT_K7_NUTTX)')
def bounds(signature):
 a=s.index(signature);b=s.index('{',a);depth=1;i=b+1
 while depth:
  if s[i]=='{':depth+=1
  if s[i]=='}':depth-=1
  i+=1
 return a,b,i
# Exclude entire unsupported helper functions (no NuttX unresolved munmap/nftw).
for sig in ['static void UnmapFile(', 'int nftw_remove(']:
 a,b,e=bounds(sig);s=s[:a]+'#if !defined(ORT_K7_NUTTX)\n'+s[a:e]+'\n#endif'+s[e:]
# Explicit refusal rather than synthetic capability success.
items=[('  Status MapFileIntoMemory(', '(void)file_path; (void)offset; (void)length; (void)mapped_memory;'),('  common::Status CreateFolder(', '(void)path;'),('  common::Status DeleteFolder(', '(void)path;'),('  common::Status FileOpenWr(', '(void)path; fd = -1;'),('  common::Status GetCanonicalPath(', '(void)path; (void)canonical_path;'),('  common::Status LoadDynamicLibrary(', '(void)library_filename; (void)global_symbols; if(handle) *handle=nullptr;'),('  common::Status UnloadDynamicLibrary(', '(void)handle;'),('  common::Status GetSymbolFromLibrary(', '(void)handle; (void)symbol_name; if(symbol) *symbol=nullptr;')]
for sig,args in items:
 a,b,e=bounds(sig);s=s[:b+1]+'\n#if defined(ORT_K7_NUTTX)\n    '+args+'\n    return common::Status(common::ONNXRUNTIME, common::NOT_IMPLEMENTED, "Unsupported by K7 Env gate");\n#else'+s[b+1:e-1]+'\n#endif\n  '+s[e-1:]
s=s.replace('    return std::max(1, static_cast<int>(std::thread::hardware_concurrency() / 2));','''#if defined(ORT_K7_NUTTX)
    return 1; // Conservative default parallelism, NOT measured physical topology.
#else
    return std::max(1, static_cast<int>(std::thread::hardware_concurrency() / 2));
#endif''')
s=s.replace('    if (custom_create_thread_fn) {','''#if defined(ORT_K7_NUTTX)
    ORT_ENFORCE(!param_ptr->affinity.has_value() || param_ptr->affinity->empty(),
                "K7 Env gate does not implement explicit affinity");
    ORT_ENFORCE(!custom_create_thread_fn || custom_join_thread_fn,
                "K7 custom thread requires a matching join callback");
#endif
    if (custom_create_thread_fn) {''',1)
s=s.replace('      size_t stack_size = thread_options.stack_size;','''#if defined(ORT_K7_NUTTX)
      struct AttrGuard { pthread_attr_t* p; ~AttrGuard() { pthread_attr_destroy(p); } } attr_guard{&attr};
#endif
      size_t stack_size = thread_options.stack_size;''')
s=s.replace('    if (buf.st_size < 0) {','''#if defined(ORT_K7_NUTTX)
    ORT_RETURN_IF_NOT(S_ISREG(buf.st_mode), "K7 requires regular model files");
#endif
    if (buf.st_size < 0) {''')
s=s.replace('    if (length == 0)\n      return Status::OK();','''#if defined(ORT_K7_NUTTX)
    size_t file_size = 0;
    ORT_RETURN_IF_ERROR(GetFileLength(file_descriptor.Get(), file_size));
    ORT_RETURN_IF_NOT(static_cast<uint64_t>(offset) <= file_size &&
                      length <= file_size - static_cast<size_t>(offset), "K7 read outside file");
#endif
    if (length == 0)
      return Status::OK();''',1)
s=s.replace('      constexpr size_t k_max_bytes_to_read = 1 << 30;  // read at most 1GB each time','''#if defined(ORT_K7_NUTTX)
      constexpr size_t k_max_bytes_to_read = 65536;
#else
      constexpr size_t k_max_bytes_to_read = 1 << 30;  // read at most 1GB each time
#endif''')
s=s.replace('      while (nanosleep(&sleep_time, &sleep_time) != 0 && errno == EINTR) {\n        // Ignore signals and wait for the full interval to elapse.\n      }', '''#if defined(ORT_K7_NUTTX)
      while (nanosleep(&sleep_time, &sleep_time) != 0) {
        if (errno != EINTR) ORT_THROW("K7 nanosleep failed: ", errno);
      }
#else
      while (nanosleep(&sleep_time, &sleep_time) != 0 && errno == EINTR) {
        // Ignore signals and wait for the full interval to elapse.
      }
#endif''')
(p/'env-gate.cc').write_text(s)
(p/'env-gate.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/onnxruntime/core/platform/posix/env.cc',tofile='b/onnxruntime/core/platform/posix/env.cc')))
print('Env conditional patch prepared (not full-ORT compiled)')
