from pathlib import Path
import datetime, tarfile, difflib
r=Path('/home/swl/openvela'); w=r/'work/rk3576-usbhost'
paths=['apps/examples/k7host/k7host_main.c','nuttx/drivers/usbhost/usbhost_xhci_rk3576.c']
with tarfile.open(w/('pre-uvc-control-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz'),'w:gz') as z:
    for name in paths:z.add(r/name,arcname=name)
patch=[]
for name in paths:
    p=r/name; old=p.read_text(); new=old
    if name.endswith('k7host_main.c'):
        new=new.replace('req, buffer);','req, len ? buffer : NULL);')
    else:
        a='''  if (req->type & USB_REQ_DIR_IN)
    {
      trt = XHCI_TRB_D2_TRT_INDATA;
    }
  else if (req->type & USB_REQ_DIR_OUT)
    {
      trt = XHCI_TRB_D2_TRT_OUTDATA;
    }
  else
    {
      trt = XHCI_TRB_D2_TRT_NODATA;
    }'''
        b='''  /* OUT direction is encoded as zero, so it cannot be tested with &.
   * wLength determines whether a data stage exists. */
  if (buflen == 0)
    {
      trt = XHCI_TRB_D2_TRT_NODATA;
    }
  else if (req->type & USB_REQ_DIR_IN)
    {
      trt = XHCI_TRB_D2_TRT_INDATA;
    }
  else
    {
      trt = XHCI_TRB_D2_TRT_OUTDATA;
    }'''
        assert a in new; new=new.replace(a,b)
        i=new.index('static int xhci_control_setup(',new.index('static int xhci_control_setup(')+1)
        j=new.index('static int xhci_normal_setup(',i)
        part=new[i:j].replace('if (buffer)','if (buffer && buflen)')
        part=part.replace('if (!(req->type & USB_REQ_DIR_IN))','if (buflen == 0 || !(req->type & USB_REQ_DIR_IN))')
        new=new[:i]+part+new[j:]
    assert new!=old
    p.write_text(new)
    patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(w/'uvc-control-v10.patch').write_text(''.join(patch))
print('Fixed control transfer direction and zero-length data-stage handling')
