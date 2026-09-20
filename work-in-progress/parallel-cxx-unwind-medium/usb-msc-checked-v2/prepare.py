"""Generate candidate only; defaults preserve frozen original function bodies."""
import difflib
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'evidence/usb-storage-inputs-20260910/nuttx'

def function_span(text,name):
    # Definitions follow the first Private Data marker; skip prototypes.
    import re
    for m in re.finditer(r'\b'+re.escape(name)+r'\s*\(',text):
        pos=m.end(); depth=1
        while depth:
            if text[pos]=='(': depth+=1
            if text[pos]==')': depth-=1
            pos+=1
        while text[pos].isspace(): pos+=1
        if text[pos]!='{': continue
        begin=pos; depth=1; pos+=1
        # GCC sources in selected functions have balanced braces in comments.
        while depth:
            if text[pos]=='{': depth+=1
            if text[pos]=='}': depth-=1
            pos+=1
        return begin,pos
    raise ValueError(name)

def wrap(text,name,body):
    a,b=function_span(text,name)
    return text[:a]+'{\n#ifdef CONFIG_USBHOST_MSC_READONLY\n'+body+'\n#else\n'+text[a+1:b-1]+'\n#endif\n}'+text[b:]

def generate():
    source=BASE/'drivers/usbhost/usbhost_storage.c'
    old=source.read_text(encoding='utf-8'); new=old
    anchor='  volatile bool           disconnected;'
    i=new.index(anchor)
    new=new[:i]+'''#ifdef CONFIG_USBHOST_MSC_READONLY
  bool                    bot_failed;   /* Latched until a new instance */
  uint32_t                next_tag;
#endif
'''+new[i:]
    i=new.index('static inline int usbhost_maxlunreq(',new.index(' * Name: Command helpers'))
    new=new[:i]+(HERE/'checked.inc').read_text(encoding='utf-8')+'\n\n'+new[i:]
    for name,builder,length,allow in [
        ('usbhost_testunitready','usbhost_testunitreadycbw','0','true'),
        ('usbhost_requestsense','usbhost_requestsensecbw','SCSIRESP_FIXEDSENSEDATA_SIZEOF','false'),
        ('usbhost_inquiry','usbhost_inquirycbw','SCSIRESP_INQUIRY_SIZEOF','false')]:
        new=wrap(new,name,'''  FAR struct usbmsc_cbw_s *cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      return -ENOMEM;
    }

  %s(cbw);
  return usbhost_checked_command(priv, cbw, priv->tbuffer, %s, %s);'''%(builder,length,allow))
    new=wrap(new,'usbhost_readcapacity','  return usbhost_checked_capacity(priv);')
    new=wrap(new,'usbhost_read','  return usbhost_checked_read(inode, buffer, startsector, nsectors);')
    new=wrap(new,'usbhost_write','''  (void)inode;
  (void)buffer;
  (void)startsector;
  (void)nsectors;
  return -EROFS;''')
    new=wrap(new,'usbhost_geometry','''  FAR struct usbhost_state_s *priv = inode->i_private;
  int ret;
  if (geometry == NULL)
    {
      return -EINVAL;
    }

  ret = nxmutex_lock(&priv->lock);
  if (ret < 0)
    {
      return ret;
    }

  memset(geometry, 0, sizeof(*geometry));
  if (priv->disconnected || priv->bot_failed)
    {
      ret = -ENODEV;
    }
  else
    {
      geometry->geo_available = true;
      geometry->geo_writeenabled = false;
      geometry->geo_nsectors = priv->nblocks;
      geometry->geo_sectorsize = priv->blocksize;
      ret = OK;
    }

  nxmutex_unlock(&priv->lock);
  return ret;''')
    a,b=function_span(new,'usbhost_cbwalloc')
    body=new[a:b]
    body=body.replace('  return cbw;', '''#ifdef CONFIG_USBHOST_MSC_READONLY
  usbhost_putle32(cbw->tag, ++priv->next_tag);
#endif
  return cbw;''')
    new=new[:a]+body+new[b:]
    # Fail new opens under the same class lock; do not fake disconnect state.
    a,b=function_span(new,'usbhost_open'); body=new[a:b]
    body=body.replace('if (priv->disconnected)','''if (priv->disconnected
#ifdef CONFIG_USBHOST_MSC_READONLY
      || priv->bot_failed
#endif
     )''',1)
    new=new[:a]+body+new[b:]
    # Do not hide non-stall GET_MAX_LUN transport errors in checked mode.
    a,b=function_span(new,'usbhost_maxlunreq'); body=new[a:b]
    body=body.replace('  if (ret < 0)', '''#ifdef CONFIG_USBHOST_MSC_READONLY
  if (ret < 0 && ret != -EPERM)
    {
      return usbhost_bot_failed(priv);
    }
#endif
  if (ret < 0)''',1)
    new=new[:a]+body+new[b:]
    a,b=function_span(new,'usbhost_initvolume'); body=new[a:b]
    body=body.replace('  ret = usbhost_maxlunreq(priv);','''  ret = usbhost_maxlunreq(priv);
#ifdef CONFIG_USBHOST_MSC_READONLY
  if (ret < 0)
    {
      goto checked_done;
    }
#endif''')
    anchor='  /* Decrement the reference count.  We incremented the reference count'
    body=body.replace(anchor,'''#ifdef CONFIG_USBHOST_MSC_READONLY
checked_done:
#endif
'''+anchor)
    new=new[:a]+body+new[b:]
    kold=(BASE/'drivers/usbhost/Kconfig').read_text(encoding='utf-8')
    knew=kold.replace('config USBHOST_MSC_NOTIFIER\n','''config USBHOST_MSC_READONLY
\tbool "Checked read-only USB MSC diagnostic mode"
\tdefault n
\tdepends on USBHOST_MSC
\t---help---
\t\tReject block writes, report read-only geometry and restrict READ10 to
\t\t4 KiB with checked capacity and exact BOT response lengths. Transport
\t\tor protocol errors disable this class instance until re-enumeration.
\t\tThis conservative mode applies to all MSC instances; it does not add
\t\tBOT reset recovery or support for read-only FAT mounts.

config USBHOST_MSC_NOTIFIER
''')
    changes=[('drivers/usbhost/usbhost_storage.c',old,new),('drivers/usbhost/Kconfig',kold,knew)]
    diff=[]
    for rel,previous,current in changes:
        p=HERE/'candidate'/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(current,encoding='utf-8')
        diff.extend(difflib.unified_diff(previous.splitlines(True),current.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
    (HERE/'candidate.patch').write_text(''.join(diff),encoding='utf-8')
    print('Generated unapplied two-file checked MSC candidate')

if __name__=='__main__': generate()
