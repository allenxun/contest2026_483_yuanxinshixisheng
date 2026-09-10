# -*- coding: utf-8 -*-
"""pytest 根配置：把 backend/acceptance 置于 sys.path 并加载 E 验收插件。

真正的钩子实现位于 framework/conftest.py（marker 注册、dependency_pending
统计、matrix 退出码=3）。rootdir 由本目录 pytest.ini 锚定，故此处为顶层
conftest，pytest_plugins 声明合法。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest_plugins = ("framework.conftest",)
