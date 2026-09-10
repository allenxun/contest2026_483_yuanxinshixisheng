# -*- coding: utf-8 -*-
"""SC-02 · 测肤任务、补拍与报告归档 —— 11 个场景节点（与清单 ID 一一对应）。

执行统一走基线门控 framework/gate.py：
- baseline gate=closed（当前）：节点 skip 且 reason 前缀 "dependency_pending: "，
  由插件统计为 dependency_pending，matrix 退出码 3。
- gate=open 且步骤未编写：节点 fail("scenario steps not yet authored")。

TODO(A-baseline 交付后)：为本节每个场景按 matrix/scenarios.json 的 checkpoints
逐条编写黑盒 HTTP 步骤（framework/client.py + isolation run-id 夹具 +
doubles 声明），替换本工厂生成的门控函数；测试名保留场景 ID 以维持追溯。
"""
from framework.gate import make_scenario_tests

MODULE = "SC-02"
globals().update(make_scenario_tests(MODULE))
