from pathlib import Path
import re,hashlib,json
p=Path(__file__).parent; old=p.parent/'voice-radio-backend-v1';(p/'candidate').mkdir(exist_ok=True)
a=[]
for n in ['voice_wifi_adapter.cpp','voice_wifi_adapter.hpp','test_adapter.cpp']:
 b=(old/n).read_bytes();(p/('old-'+n)).write_bytes(b);a.append({'path':str(old/n),'sha256':hashlib.sha256(b).hexdigest()})
 s=b.decode().replace("\r\n","\n");s=re.sub(r'\bwd_', 'k7wd_',s)
 if n.endswith('.hpp'):
  s=s.replace('#include "wifi_scan.h"','#include "wifi_scan.h"\n#include "k7_radio_service.h"')
  s=s.replace('std::uint64_t timeout_ms=30000)\n', 'std::uint64_t timeout_ms=30000) noexcept\n')
  s=s.replace('\n};\n}\n','\n};\n// Nullopt until the real process-lifetime radio service is published.\n// Caller owns this optional; create once on the serial Controller task.\nstd::optional<SharedWifiPort> nativeWifiPort(std::uint64_t timeout_ms=30000) noexcept;\n}\n')
 if n=='voice_wifi_adapter.cpp':
  s=s.replace('namespace voicelink {','''namespace voicelink {
std::optional<SharedWifiPort> nativeWifiPort(std::uint64_t timeout_ms) noexcept {
 auto *d=k7_wifi_dispatch(); auto *s=k7_wifi_scans();
 if(!timeout_ms || !d || !s || s->d!=d || d->scan!=s) return std::nullopt;
 return std::optional<SharedWifiPort>(std::in_place,*d,*s,timeout_ms);
}
''',1)
  s=s.replace('  try {char ip[16];','''#if defined(__cpp_exceptions)
  try {
#endif
   char ip[16];''').replace('r.status=ConnectStatus::IpReady;} catch(...) {r.error_code=-12;}','''r.status=ConnectStatus::IpReady;
#if defined(__cpp_exceptions)
  } catch(...) {r.error_code=-12;}
#endif''')
 if n=='test_adapter.cpp':
  s=s.replace('using namespace voicelink;','''using namespace voicelink;
static k7wd_dispatch *native_d;
static ws_service *native_s;
extern "C" k7wd_dispatch *k7_wifi_dispatch(void) {return native_d;}
extern "C" ws_service *k7_wifi_scans(void) {return native_s;}
''')
  extra='''static bool zero_bytes(const void*p,size_t n){const unsigned char*b=(const unsigned char*)p;while(n--)if(*b++)return false;return true;}
static void native_and_credentials(){
 C(!nativeWifiPort()); Fixture f;native_d=&f.d;C(!nativeWifiPort());native_s=&f.s;
 C(!nativeWifiPort(0));auto port=nativeWifiPort();C(port.has_value());
 char password[]="12345678";auto a=port->beginConnect("AP1",password,8);
 C(a.status==ConnectStatus::CredentialsReceived);std::memset(password,0,8);
 C(std::memcmp(f.d.requests[f.d.rq_head].credentials.password,"12345678",8)==0);
 port->cancelConnect(a.request_id);
 C(zero_bytes(&f.d.requests[f.d.rq_head].credentials,sizeof(wb_job)));
 f.pump();C(f.joins==0&&port->pollConnect(a.request_id).status==ConnectStatus::Cancelled);
 auto b=port->beginConnect("AP1","87654321",8);port->cancelConnect(a.request_id);f.pump();
 C(f.joins==1&&port->pollConnect(b.request_id).status==ConnectStatus::Connecting);
 C(zero_bytes(&f.d.requests[0].credentials,sizeof(wb_job)));
 C(zero_bytes(&f.d.requests[1].credentials,sizeof(wb_job)));
 C(zero_bytes(&f.d.broker.pending,sizeof(wb_job)));
 C(std::memcmp(f.job.password,"87654321",8)==0); /* explicit mock backend owns copied secret */
 wb_job_clear(&f.job);C(zero_bytes(&f.job,sizeof(f.job)));
 C(k7wd_ble_cancel(&f.d,b.request_id)==WD_FORBIDDEN);
 port->cancelConnect(b.request_id);f.pump();C(f.d.broker.radio==WB_DRAINING);
 native_d=nullptr;native_s=nullptr;
}
'''
  s=s.replace('int main(){',''+extra+'int main(){native_and_credentials();')
 (p/'candidate'/n).write_text(s)
(p/'old-inputs.json').write_text(json.dumps(a,indent=2))
print('prepared candidate binding and tests')



