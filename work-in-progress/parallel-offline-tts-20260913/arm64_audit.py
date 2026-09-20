"""Compile and demand-link without writing to the read-only Ubuntu tree.

The compiler/linker inputs and outputs use anonymous Linux memfd handles. Only
the returned objects, logs, and audit JSON are written, all in this WIP folder.
"""
import base64
import hashlib
import json
import shlex
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VOICE = ROOT / "work-in-progress/voice-ui-connect-20260913"
KEY = "C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519"
KNOWN = "C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts"
HOST = "swl@192.168.152.131"
SSH = ["ssh.exe", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes",
       "-o", "UserKnownHostsFile=" + KNOWN, HOST]
CURRENT = "/home/swl/openvela/work/velavision-project/work-in-progress/voice-ui-connect-20260913/runtime.o"
TOOL = "/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def remote(command, payload, name):
    helper = r'''import json,os,subprocess,sys
args=json.loads(sys.argv[1]); data=sys.stdin.buffer.read()
inf=os.memfd_create("k7-input",0); outf=os.memfd_create("k7-output",0)
for offset in range(0,len(data),1048576): os.write(inf,data[offset:offset+1048576])
os.lseek(inf,0,0)
args=[x.replace("{IN}","/proc/self/fd/%d"%inf).replace("{OUT}","/proc/self/fd/%d"%outf) for x in args]
p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(inf,outf))
sys.stderr.buffer.write(p.stdout);sys.stderr.buffer.write(p.stderr)
if p.returncode: raise SystemExit(p.returncode)
os.lseek(outf,0,0)
while True:
 b=os.read(outf,1048576)
 if not b: break
 sys.stdout.buffer.write(b)
'''
    launcher = "python3 -c " + shlex.quote(helper) + " " + shlex.quote(json.dumps(command))
    p = subprocess.run(SSH + [launcher], input=payload, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=300)
    (HERE / (name + ".log")).write_bytes(p.stderr)
    if p.returncode:
        raise RuntimeError(name + " failed; inspect " + name + ".log")
    return p.stdout

def audit(candidate, combined):
    helper = r'''import hashlib,json,os,subprocess,sys
raw=sys.stdin.buffer.read(); n=int.from_bytes(raw[:8],"little"); a=raw[8:8+n]; b=raw[8+n:]
fd1=os.memfd_create("candidate",0);fd2=os.memfd_create("combined",0)
os.write(fd1,a);os.write(fd2,b);os.lseek(fd1,0,0);os.lseek(fd2,0,0)
p1="/proc/self/fd/%d"%fd1;p2="/proc/self/fd/%d"%fd2
current=sys.argv[1]; base=sys.argv[2]
def output(tool,*args):return subprocess.check_output([base+tool,*args],text=True,pass_fds=(fd1,fd2))
def und(path):
 ans=[]
 for line in output("aarch64-none-elf-nm","-u",path).splitlines():
  q=line.split()
  if q and (q[-2] if len(q)>1 else "") in ("U","u"):ans.append(q[-1])
 return sorted(set(ans))
def defs(path):
 ans=[]
 for line in output("aarch64-none-elf-nm","-g","--defined-only",path).splitlines():
  q=line.split()
  if len(q)>=3 and q[-2].upper() not in ("U","W","V"):ans.append(q[-1])
 return ans
def sec(path):
 s=output("aarch64-none-elf-readelf","-SW",path)
 return {"eh_frame": ".eh_frame" in s, "gcc_except_table": ".gcc_except_table" in s}
ua,ub,uc=und(p1),und(p2),und(current);db=defs(p2)
result={"candidate_undefined":ua,"candidate_strong_undefined_count":len(ua),
 "combined_strong_undefined_count":len(ub),"current_strong_undefined_count":len(uc),
 "added_combined_undefined":sorted(set(ub)-set(uc)),"removed_combined_undefined":sorted(set(uc)-set(ub)),
 "candidate_sections":sec(p1),"combined_sections":sec(p2),
 "combined_emutls_definition_count":db.count("__emutls_get_address"),
 "combined_tts_entry_definition_count":db.count("k7_tts_synthesize"),
 "current_sha256":hashlib.sha256(open(current,"rb").read()).hexdigest()}
print(json.dumps(result))
'''
    launcher = "python3 -c " + shlex.quote(helper) + " " + shlex.quote(CURRENT) + " " + shlex.quote(TOOL)
    payload = len(candidate).to_bytes(8, "little") + candidate + combined
    p = subprocess.run(SSH + [launcher], input=payload, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=180)
    (HERE / "arm64-symbol-audit.log").write_bytes(p.stderr)
    if p.returncode:
        raise RuntimeError("symbol audit failed; inspect arm64-symbol-audit.log")
    return json.loads(p.stdout.decode("utf-8"))

voice_result = json.loads((VOICE / "result.json").read_text(encoding="utf-8-sig"))
command = list(voice_result["compile"][0]["command"])
command[command.index("-c") + 1] = "{IN}"
command[command.index("-o") + 1] = "{OUT}"
command = ["-DSHERPA_ONNX_ENABLE_TTS=1" if x == "-DSHERPA_ONNX_ENABLE_TTS=0" else x
           for x in command]
command[command.index("-c"):command.index("-c")] = ["-x", "c++"]
source_path = HERE / "native_tts_runtime.cpp"
header_path = HERE / "include/voicelink/tts_runtime.h"
source = source_path.read_text(encoding="utf-8")
header = header_path.read_text(encoding="utf-8")
needle = '#include "voicelink/tts_runtime.h"'
if source.count(needle) != 1:
    raise RuntimeError("unexpected public header include")
materialized = source.replace(needle, header)
candidate = remote(command, materialized.encode("utf-8"), "arm64-compile")
(HERE / "native_tts_runtime.arm64.o").write_bytes(candidate)

ld = TOOL + "aarch64-none-elf-ld"
link_command = [ld, "-r", "--strip-debug", "-o", "{OUT}", CURRENT, "{IN}"]
combined = remote(link_command, candidate, "arm64-demand-link")
(HERE / "tts-with-current-asr.arm64.o").write_bytes(combined)
symbols = audit(candidate, combined)

result = {
    "status": "pass" if not symbols["added_combined_undefined"] and
              symbols["combined_emutls_definition_count"] == 1 and
              symbols["combined_tts_entry_definition_count"] == 1 else "fail",
    "method": "Ubuntu SDK/tree read-only; source and objects transported over SSH; remote compile/link used anonymous memfd only",
    "source_sha256": sha(source_path.read_bytes()),
    "header_sha256": sha(header_path.read_bytes()),
    "materialized_translation_unit_sha256": sha(materialized.encode("utf-8")),
    "compile_command": command,
    "candidate_object": {"bytes": len(candidate), "sha256": sha(candidate)},
    "current_asr_runtime": {"path": CURRENT, "sha256": symbols.pop("current_sha256")},
    "link_command": link_command,
    "combined_object": {"bytes": len(combined), "sha256": sha(combined)},
    "symbols": symbols,
    "firmware_linked": False,
    "board_tested": False
}
(HERE / "arm64-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "candidate": result["candidate_object"],
                  "combined": result["combined_object"], "symbols": symbols}, indent=2))
if result["status"] != "pass":
    raise SystemExit(1)
