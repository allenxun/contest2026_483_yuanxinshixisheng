"""Restore the pinned PyUSB wheel into the local, non-system vendor directory."""

import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
TARGET = HERE / "vendor" / "pyusb"
URL = (
    "https://files.pythonhosted.org/packages/28/b8/"
    "27e6312e86408a44fe16bd28ee12dd98608b39f7e7e57884a24e8f29b573/"
    "pyusb-1.3.1-py3-none-any.whl"
)
SHA256 = "bf9b754557af4717fe80c2b07cc2b923a9151f5c08d17bdb5345dac09d6a0430"


def main():
    if (TARGET / "usb" / "__init__.py").is_file():
        print("PYUSB_ALREADY_PRESENT=" + str(TARGET))
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="velavision-pyusb-") as temp:
        wheel = Path(temp) / "pyusb-1.3.1-py3-none-any.whl"
        urllib.request.urlretrieve(URL, wheel)
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError("PyUSB wheel SHA256 mismatch")
        unpacked = Path(temp) / "unpacked"
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(unpacked)
        if not (unpacked / "usb" / "__init__.py").is_file():
            raise RuntimeError("PyUSB wheel layout mismatch")
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.move(str(unpacked), str(TARGET))
    print("PYUSB_RESTORED=" + str(TARGET))


if __name__ == "__main__":
    main()
