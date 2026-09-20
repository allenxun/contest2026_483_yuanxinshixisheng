from pathlib import Path
import json,hashlib,difflib
p=Path(__file__).parent;r=Path('E:/openvela/VelaVision');src=r/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d';(p/'input').mkdir(exist_ok=True)
paths=['onnxruntime/core/platform/posix/env.cc','onnxruntime/core/graph/model.cc','onnxruntime/core/framework/tensorprotoutils.cc','include/onnxruntime/core/platform/EigenNonBlockingThreadPool.h','orttraining/orttraining/core/framework/checkpointing.cc']
a=[]
for i,n in enumerate(paths):
 b=(src/n).read_bytes();q='input/'+str(i)+'-'+Path(n).name;(p/q).write_bytes(b);a.append({'path':str(src/n),'snapshot':q,'sha256':hashlib.sha256(b).hexdigest()})
v1=r/'work-in-progress/parallel-model-reader-medium/native-ort-env-gate-v1/env-gate.cc';b=v1.read_bytes();(p/'input/v1-env-gate.cc').write_bytes(b);a.append({'path':str(v1),'snapshot':'input/v1-env-gate.cc','sha256':hashlib.sha256(b).hexdigest()})
(p/'inputs.json').write_text(json.dumps(a,indent=2));s=b.decode().replace("\r\n","\n");old=s
s=s.replace('#include <pthread.h>','#include <pthread.h>\n#include <exception>')
s=s.replace('    ORT_ENFORCE(!custom_create_thread_fn || custom_join_thread_fn,\n                "K7 custom thread requires a matching join callback");','    ORT_ENFORCE(!custom_create_thread_fn && !custom_join_thread_fn,\n                "K7 gate uses checked native pthread ownership only");')
s=s.replace('''#ifdef NDEBUG
      pthread_join(hThread, &res);
#else
      int ret = pthread_join(hThread, &res);
      assert(ret == 0);
#endif''','''#if defined(ORT_K7_NUTTX)
      const int ret = pthread_join(hThread, &res);
      if (ret != 0) {
        // Returning would free pool queues still reachable by a live worker.
        // This is a fatal invariant failure, not cancellation/recovery.
        std::terminate();
      }
#elif defined(NDEBUG)
      pthread_join(hThread, &res);
#else
      int ret = pthread_join(hThread, &res);
      assert(ret == 0);
#endif''')
a0=s.index('  PosixThread(');a1=s.index('  ~PosixThread()',a0);section=s[a0:a1]
section=section.replace('auto [err_no, err_msg] = GetSystemError();','#if defined(ORT_K7_NUTTX)\n        auto [err_no, err_msg] = GetSystemError(s);\n#else\n        auto [err_no, err_msg] = GetSystemError();\n#endif')
s=s[:a0]+section+s[a1:]
anchor='''    fd = open(path.c_str(), O_RDONLY);
    if (0 > fd) {
      return ReportSystemError("open", path);
    }
    return Status::OK();'''
replacement='''    fd = open(path.c_str(), O_RDONLY);
    if (0 > fd) {
      return ReportSystemError("open", path);
    }
#if defined(ORT_K7_NUTTX)
    struct stat sb;
    const int stat_result = fstat(fd, &sb);
    const int error = stat_result != 0 ? (errno ? errno : EIO) :
                      (!S_ISREG(sb.st_mode) || sb.st_size < 0 ? EINVAL : 0);
    if (error) {
      // Keep SYSTEM status: Model::Load helper handles these before using fd.
      const int close_result = close(fd);
      fd = -1;
      if (close_result != 0) return ReportSystemError("close", "");
      return common::Status(common::SYSTEM, error, "K7 model fd is not a regular file");
    }
#endif
    return Status::OK();'''
assert s.count(anchor)==1;s=s.replace(anchor,replacement)
assert s!=old
(p/'env-gate.cc').write_text(s)
(p/'v1-to-v2.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/onnxruntime/core/platform/posix/env.cc',tofile='b/onnxruntime/core/platform/posix/env.cc')))
base=(p/'input/0-env.cc').read_text()
(p/'full-env-gate.patch').write_text(''.join(difflib.unified_diff(base.splitlines(True),s.splitlines(True),fromfile='a/onnxruntime/core/platform/posix/env.cc',tofile='b/onnxruntime/core/platform/posix/env.cc')))
print('v2 prepared; full ORT not compiled')

