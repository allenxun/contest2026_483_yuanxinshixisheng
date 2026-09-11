"""支持 ``python -m mvp_worker.scanners``（需 __main__.py 才会执行包入口）。"""
from __future__ import annotations

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
