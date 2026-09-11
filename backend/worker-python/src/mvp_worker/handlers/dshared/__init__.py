"""D 包（测肤分析 / 身份登记 / 方案生成）Worker 侧共享支撑。

本包由 D 任务包维护，只被 ``mvp_worker.handlers`` 下的三个 D handler 与
D 测试引用。它不修改 A 包运行时、配置或媒体骨架，只提供：

- :mod:`constants`：跨语言固定命名空间等常量；
- :mod:`dconfig`：D 包 env 配置与受控基线（供应商、namespace、指标白名单等）；
- :mod:`providers`：人脸/测肤/方案端口 + 可控替身 + 阿里云形状边界 + 工厂；
- :mod:`jsonschema_support`：payload 契约严格校验（复用 common.json $ref 内联）；
- :mod:`denqueue`：worker 侧 T12 入队助手（去重 / 部分唯一索引冲突区分）；
- :mod:`dmedia`：结果图归档（T11 行 + 存储写入，幂等复用）；
- :mod:`resolve`：端口解析（extras 注入优先，否则按 env/环境工厂，生产 fail-closed）。
"""
