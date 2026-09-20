"""Generate review-only candidate and patch; never modify formal inputs."""
import pathlib,json,hashlib,difflib
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=json.loads((ROOT.parent/'inputs.json').read_text(encoding='utf-8'))
for path,digest in lock.items():
 if sha(PROJECT/path)!=digest:raise SystemExit('frozen input changed: '+path)
def replace(s,a,b):
 if s.count(a)!=1:raise SystemExit('anchor not unique: '+a)
 return s.replace(a,b)
path='app/k7radio/skw_wifi_amsdu.h'
old=(PROJECT/path).read_text(encoding='utf-8');s=old
s=replace(s,'struct skw_amsdu_rx {','#include "skw_wifi_pn_diag.h"\nstruct skw_amsdu_rx {')
s=replace(s,'static inline int skw_amsdu_receive(','static inline int skw_amsdu_receive_diag(')
s=replace(s,'uint64_t now_ms,int (*deliver)(const uint8_t *,size_t))','uint64_t now_ms,int (*deliver)(const uint8_t *,size_t),struct skw_pn_diag *diag)')
s=replace(s,'if(v.pn<=*floor)return -EACCES;','if(v.pn<=*floor)return skw_pn_reject(diag,SKW_PN_FLOOR,&v,*floor,p,now_ms);')
s=replace(s,'if(p->active && v.pn<p->pn)return -EACCES;','if(p->active && v.pn<p->pn)return skw_pn_reject(diag,SKW_PN_PENDING_NEWER,&v,*floor,p,now_ms);')
s=replace(s,'if(p->pn!=v.pn || p->sequence!=v.sequence)return -EACCES;','if(p->pn!=v.pn || p->sequence!=v.sequence)return skw_pn_reject(diag,SKW_PN_PENDING_TUPLE,&v,*floor,p,now_ms);')
s=replace(s,'if(p->bitmap&(1u<<v.index))return -EACCES;','if(p->bitmap&(1u<<v.index))return skw_pn_reject(diag,SKW_PN_DUPLICATE_INDEX,&v,*floor,p,now_ms);')
s=replace(s,'#endif','''/* Preserve original caller ABI; diagnostics are opt-in. */
static inline int skw_amsdu_receive(struct skw_amsdu_rx *a,struct skw_data_replay *r,
 const uint8_t *slot,size_t size,uint8_t instance,uint8_t peer,const uint8_t own[6],
 uint64_t now_ms,int (*deliver)(const uint8_t *,size_t))
{return skw_amsdu_receive_diag(a,r,slot,size,instance,peer,own,now_ms,deliver,NULL);}
#endif''')
(ROOT/'skw_wifi_amsdu.h').write_text(s,encoding='utf-8')
patch=''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),'a/'+path,'b/'+path))
path='app/k7radio/wifi_ip_service.inc'
old=(PROJECT/path).read_text(encoding='utf-8');s=old
s=replace(s,'static struct skw_amsdu_rx g_wifi_amsdu;','''static struct skw_amsdu_rx g_wifi_amsdu;
/* RX-owner-only, first 16 rate-limited PN decisions per firmware lifetime.
 * No asynchronous reader, reset or receive-path printing is added. */
static struct skw_pn_diag g_wifi_pn_diag;''')
s=replace(s,'int ret=skw_amsdu_receive(&g_wifi_amsdu,','int ret=skw_amsdu_receive_diag(&g_wifi_amsdu,')
s=replace(s,'now_us()/1000,skw_netdev_rx);','now_us()/1000,skw_netdev_rx,&g_wifi_pn_diag);')
(ROOT/'wifi_ip_service.inc').write_text(s,encoding='utf-8')
patch+=''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),'a/'+path,'b/'+path))
path='app/k7radio/skw_wifi_pn_diag.h';s=(ROOT/'skw_wifi_pn_diag.h').read_text(encoding='utf-8')
patch+=''.join(difflib.unified_diff([],s.splitlines(True),'/dev/null','b/'+path))
(ROOT/'pn-diagnostic.patch').write_text(patch,encoding='utf-8')
(ROOT/'inputs.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8')
print('Generated review-only candidates and patch; frozen input hashes verified')
