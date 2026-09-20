"""Observe only the owned K7 advertisement; never connect or pair."""
import asyncio,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'无线适配_2026-09-08/tools/ble-python-deps'))
from bleak import BleakScanner
async def main():
    result=None
    def match(device,advert):
        nonlocal result
        if device.address.upper()!='60:48:9C:B5:17:1D':return False
        if '6b7a0001-78c3-4f2e-9c2f-3ecbc2d74680' not in advert.service_uuids:return False
        result=dict(time=datetime.now(timezone.utc).isoformat(),address=device.address,
                    name=advert.local_name,service_uuids=advert.service_uuids,connected=False)
        return True
    assert await BleakScanner.find_device_by_filter(match,timeout=15),'Owned provision service advertisement absent'
    (ROOT/'evidence/phone-pairing-20260909/advertisement.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
asyncio.run(main())
