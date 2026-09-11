"""B 包通知投递支撑：推送端口 + dev/test 替身、会话核实探针、可配置参数。

本包只被 Worker 侧使用（投递只在 worker 发生）；Java 侧不导入。
真实供应商未接入：所有替身仅在 dev/test 生效，生产 fail-closed（见 push.py /
session_probe.py 的 build_* 函数）。
"""
