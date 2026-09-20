import os,sys,subprocess,json,time
from pathlib import Path
here=Path(__file__).resolve().parent
prior=here.parent/'voice-rule-provision-20260912'
env=os.environ.copy();env['PYTHONPATH']=str(prior/'vendor/pyusb')
image=Path('/home/swl/openvela/work/parallel-offline-tts-20260913/k7tts.romfs')
cmd=[sys.executable,str(prior/'fastboot_ram_download.py'),str(image),'--sha256','8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f','--vid','0x18d1','--pid','0x4d00','--serial','f71a9d152132db55','--audited-running-buffer','0x40c00800:0x07000000','--result',str(here/('rom-usb-'+time.strftime('%H%M%S')+'.json'))]
subprocess.run(cmd,env=env,check=True,timeout=180)
subprocess.run([sys.executable,str(here/'load_prefix.py'),'stage-rom-noreset'],check=True,timeout=180)
