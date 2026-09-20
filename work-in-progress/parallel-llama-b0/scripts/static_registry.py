"""Deterministically derive registry retaining upstream static APIs, rejecting DL."""
from pathlib import Path
import difflib
R=Path(__file__).resolve().parents[1]
p=R/'vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/src/ggml-backend-reg.cpp'
s=p.read_text(encoding='utf8');original=s
s=s.replace('#include <filesystem>\n','')
a=s.index('#ifdef _WIN32');b=s.index('// Backend registry',a);s=s[:a]+s[b:]
a=s.index('// disable C++17');b=s.index('struct ggml_backend_reg_entry',a);s=s[:a]+s[b:]
s=s.replace('    dl_handle_ptr handle;\n','')
a=s.index('    ~ggml_backend_registry()');b=s.index('    void register_backend',a);s=s[:a]+s[b:]
s=s.replace('ggml_backend_reg_t reg, dl_handle_ptr handle = nullptr','ggml_backend_reg_t reg')
s=s.replace('backends.push_back({ reg, std::move(handle) });','backends.push_back({ reg });')
a=s.index('    ggml_backend_reg_t load_backend');b=s.index('\n};',a);s=s[:a]+s[b:]
a=s.index('// Dynamic loading');s=s[:a]+'''// B0 static-only policy: dynamic requests fail explicitly; no POSIX shims.
ggml_backend_reg_t ggml_backend_load(const char * path) {
    GGML_UNUSED(path);
    GGML_LOG_ERROR("B0: dynamic backend loading is disabled\\n");
    return nullptr;
}
void ggml_backend_unload(ggml_backend_reg_t reg) {
    GGML_UNUSED(reg);
    GGML_LOG_ERROR("B0: static backend cannot be unloaded\\n");
}
void ggml_backend_load_all() { (void) get_reg(); }
void ggml_backend_load_all_from_path(const char * path) {
    GGML_UNUSED(path);
    GGML_LOG_ERROR("B0: backend directory scanning is disabled\\n");
}
'''
out=R/'candidate/ggml-backend-reg.cpp';out.parent.mkdir(exist_ok=True)
out.write_text(s,encoding='utf8',newline='\n')
(R/'candidate/static-registry.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),
    fromfile='a/ggml/src/ggml-backend-reg.cpp',tofile='b/ggml/src/ggml-backend-reg.cpp')),encoding='utf8',newline='\n')
